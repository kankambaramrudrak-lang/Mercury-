"""Question-driven, locally sandboxed project kickoff using Codex CLI."""

from __future__ import annotations

import hashlib
import logging
import queue
import re
import shutil
import subprocess
import threading
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Protocol


class CommandResult(Protocol):
    returncode: int
    stdout: str
    stderr: str


RunCommand = Callable[..., CommandResult]
ThreadFactory = Callable[..., threading.Thread]


class ProjectBuilder:
    """Collect a project brief, ask for approval, then run local Codex in a new folder."""

    _QUESTIONS = (
        ("idea", "What should this project do?"),
        ("name", "What should I name the project?"),
        ("theme", "What look or theme should it have?"),
        ("features", "What are the main features you want?"),
        ("stack", "Which language or framework should it use?"),
        ("deadline", "When do you need it? You can say 'no deadline'."),
    )
    _MAX_ANSWER = 1000

    def __init__(
        self,
        workspace: str | Path,
        confirmation_handler: Callable[[str, str], bool],
        model: str = "llama3.2:3b",
        codex_path: str | None = None,
        run_command: RunCommand = subprocess.run,
        thread_factory: ThreadFactory = threading.Thread,
    ) -> None:
        self.workspace = Path(workspace).resolve()
        self.confirmation_handler = confirmation_handler
        self.model = model
        self.codex_path = codex_path or shutil.which("codex")
        self._run_command = run_command
        self._thread_factory = thread_factory
        self._answers: dict[str, str] | None = None
        self._question_index = 0
        self.notifications: queue.Queue[str] = queue.Queue()

    @property
    def active(self) -> bool:
        return self._answers is not None

    def begin(self, description: str = "") -> str:
        if self.active:
            return "We're already planning a project. Answer the current question or say 'cancel project'."
        self._answers = {}
        self._question_index = 0
        description = " ".join(description.split())[: self._MAX_ANSWER]
        if description:
            self._answers["idea"] = description
            self._question_index = 1
            return self._QUESTIONS[self._question_index][1]
        return self._QUESTIONS[0][1]

    def answer(self, text: str) -> str:
        if self._answers is None:
            return "No project questionnaire is open. Say 'Start project' to begin one."
        answer = " ".join(text.split())
        if answer.casefold() in {"cancel", "cancel project", "stop project"}:
            self._reset()
            return "Project planning cancelled. No folder was created."
        if not answer or len(answer) > self._MAX_ANSWER:
            return "Please give a short answer, or say 'cancel project'."
        key, _question = self._QUESTIONS[self._question_index]
        if key == "name":
            self._answers[key] = answer
        elif key == "idea":
            self._answers[key] = answer
        else:
            self._answers[key] = answer
        self._question_index += 1
        if self._question_index < len(self._QUESTIONS):
            return self._QUESTIONS[self._question_index][1]
        return self._approve_specification()

    def _approve_specification(self) -> str:
        answers = self._answers
        assert answers is not None
        name = answers.get("name", "").strip()
        slug = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")[:64]
        if not slug or slug in {".", ".."}:
            self._reset()
            return "That project name cannot be used as a folder name. Start again with a different name."
        destination = (self.workspace / slug).resolve()
        try:
            destination.relative_to(self.workspace)
        except ValueError:
            self._reset()
            return "That folder name would leave the configured workspace. No folder was created."
        if destination.exists():
            self._reset()
            return f"The project folder already exists at {destination}. I didn't change it."
        spec = self._make_spec(answers)
        details = (
            "Approve this project specification? The folder will be created only if you approve. "
            "The local coding model is llama/Ollama; it will not use cloud APIs.\n\n"
            f"Folder: {destination}\n\n{spec}"
        )
        try:
            approved = self.confirmation_handler("Approve project specification", details)
        except Exception:
            approved = False
        logging.getLogger("hercules.confirmations").info(
            "tool=approve_project_specification approved=%s", bool(approved)
        )
        self._reset()
        if not approved:
            return "Project specification was not approved. No folder was created."
        try:
            destination.mkdir()
            spec_path = destination / "SPEC.md"
            spec_path.write_text(spec, encoding="utf-8", newline="\n")
        except OSError:
            return "I couldn't create the approved project folder. No coding agent was started."
        checkpoint = self._commit_checkpoint(destination, "Project kickoff: approved specification", ["SPEC.md"])
        if not checkpoint:
            return f"The approved specification is saved at {spec_path}, but Git could not create its first checkpoint."
        if not self.codex_path:
            return f"The specification and first checkpoint are ready at {destination}. Codex CLI was not found, so no code was generated."
        thread = self._thread_factory(
            target=self._run_coder,
            args=(destination, spec_path, hashlib.sha256(spec.encode("utf-8")).hexdigest()),
            name="hercules-project-coder",
            daemon=True,
        )
        thread.start()
        return f"Project folder and specification are ready. The local coding agent has started in {destination}."

    def _run_coder(self, destination: Path, spec_path: Path, approved_spec_hash: str) -> None:
        prompt = (
            "Read the approved SPEC.md in this project. Implement one small, working first version and add tests. "
            "Work only in the current project directory. Do not read or edit other folders. Do not use the network, "
            "install packages, access accounts, automate websites, or run destructive commands. Use only dependencies "
            "already available in this project. Run the project's relevant tests if they can run without installing "
            "anything. Do not change SPEC.md. Finish by listing changed files and test results."
        )
        args = [
            self.codex_path or "codex",
            "exec",
            "--oss",
            "--local-provider",
            "ollama",
            "--model",
            self.model,
            "--sandbox",
            "workspace-write",
            "--ephemeral",
            "--ignore-user-config",
            "--cd",
            str(destination),
            "-",
        ]
        try:
            result = self._run_command(
                args,
                cwd=destination,
                input=prompt,
                text=True,
                capture_output=True,
                timeout=1800,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            self.notifications.put(f"Local coding agent could not run. The approved specification remains at {destination}.")
            return
        if result.returncode != 0:
            self.notifications.put(f"Local coding agent stopped without a checkpoint. The approved specification remains at {destination}.")
            return
        try:
            if hashlib.sha256(spec_path.read_bytes()).hexdigest() != approved_spec_hash:
                self.notifications.put(f"The coding agent changed the approved SPEC.md. Review the project folder at {destination}; no code checkpoint was made.")
                return
        except OSError:
            self.notifications.put(f"The approved specification is missing or unreadable. No code checkpoint was made in {destination}.")
            return
        intent = self._run_command(["git", "add", "--intent-to-add", "--all"], cwd=destination, capture_output=True, text=True, timeout=30, check=False)
        diff_result = self._run_command(["git", "diff", "--no-ext-diff", "--"], cwd=destination, capture_output=True, text=True, timeout=30, check=False)
        status_result = self._run_command(["git", "status", "--short"], cwd=destination, capture_output=True, text=True, timeout=30, check=False)
        if intent.returncode != 0 or diff_result.returncode != 0 or status_result.returncode != 0 or not status_result.stdout.strip():
            self.notifications.put(f"The coding agent made no reviewable changes. The approved specification remains at {destination}.")
            return
        diff_text = diff_result.stdout[:12000]
        if len(diff_result.stdout) > len(diff_text):
            diff_text += "\n\n[Diff preview clipped; inspect the project files before approving.]"
        agent_summary = (result.stdout or "").strip()[-2500:]
        review = (
            f"Review generated files in {destination}. Approve to create a Git checkpoint. "
            "Cancel leaves the files in place and uncommitted.\n\n"
            f"Files:\n{status_result.stdout[:1500]}\n\n"
            f"Diff preview:\n{diff_text}\n\n"
            f"Local agent report:\n{agent_summary}"
        )
        try:
            approved = self.confirmation_handler("Review generated project checkpoint", review)
        except Exception:
            approved = False
        logging.getLogger("hercules.confirmations").info(
            "tool=project_code_checkpoint approved=%s", bool(approved)
        )
        if not approved:
            self.notifications.put(f"Generated files remain uncommitted at {destination}. Nothing was reverted.")
            return
        if self._commit_checkpoint(destination, "Project checkpoint: initial implementation", None):
            self.notifications.put(f"The project checkpoint is saved. Review the generated project at {destination}.")
        else:
            self.notifications.put(f"Git could not create the approved checkpoint. Generated files remain at {destination}.")

    def _commit_checkpoint(self, directory: Path, message: str, paths: list[str] | None) -> bool:
        commands: list[list[str]] = []
        if not (directory / ".git").exists():
            commands.append(["git", "init", "--quiet"])
        if paths is not None:
            commands.extend([["git", "add", "--", *paths], ["git", "commit", "--quiet", "-m", message]])
        else:
            commands.extend([["git", "add", "--all"], ["git", "commit", "--quiet", "-m", message]])
        for args in commands:
            try:
                result = self._run_command(args, cwd=directory, capture_output=True, text=True, timeout=30, check=False)
            except (OSError, subprocess.SubprocessError):
                return False
            if result.returncode != 0:
                return False
        return True

    @staticmethod
    def _make_spec(answers: dict[str, str]) -> str:
        return (
            f"# {answers['name']}\n\n"
            f"## Goal\n{answers.get('idea', 'User-provided project idea not supplied.')}\n\n"
            f"## Theme\n{answers['theme']}\n\n"
            f"## Features\n{answers['features']}\n\n"
            f"## Technology\n{answers['stack']}\n\n"
            f"## Deadline\n{answers['deadline']}\n\n"
            "## Constraints\n"
            "- Keep the first implementation small and testable.\n"
            "- Do not install dependencies or access external accounts without a separate user decision.\n"
            "- Run available local tests and report their results.\n"
        )

    def _reset(self) -> None:
        self._answers = None
        self._question_index = 0
