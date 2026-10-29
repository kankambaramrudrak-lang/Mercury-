"""Constrained desktop helpers for explicitly approved local targets."""

from __future__ import annotations

import shutil
import subprocess
import webbrowser
from pathlib import Path
from typing import Callable
from urllib.parse import quote_plus, urlsplit


_BROWSERS = {"default", "chrome", "edge", "firefox"}


class DesktopTools:
    """Open exact allowlisted targets, create workspace folders, and search."""

    def __init__(
        self,
        workspace: str | Path,
        app_whitelist: tuple[str, ...] = (),
        *,
        open_url: Callable[[str], bool] | None = None,
        start_process: Callable[..., object] | None = None,
        browser_get: Callable[[str | None], object] | None = None,
        find_executable: Callable[[str], str | None] | None = None,
    ) -> None:
        self.workspace = Path(workspace).resolve()
        self._apps = {
            item.split("=", 1)[0].strip().casefold(): item.split("=", 1)[1].strip()
            for item in app_whitelist
        }
        self._open_url = webbrowser.open if open_url is None else open_url
        self._start_process = subprocess.Popen if start_process is None else start_process
        self._browser_get = webbrowser.get if browser_get is None else browser_get
        self._find_executable = shutil.which if find_executable is None else find_executable

    @property
    def app_names(self) -> tuple[str, ...]:
        return tuple(self._apps)

    def open_app(self, name: str) -> str:
        key = name.strip().casefold()
        target = self._apps.get(key)
        if target is None:
            return f"I can't open {name}; it isn't on the approved app list."

        parsed = urlsplit(target)
        if parsed.scheme == "https" and parsed.netloc:
            try:
                opened = self._open_url(target)
            except Exception:
                opened = False
            return f"Opening {name}." if opened else f"I couldn't open {name}."
        if parsed.scheme or "\x00" in target:
            return f"The approved target for {name} isn't a supported app path."

        executable = str(Path(target)) if Path(target).is_file() else self._find_executable(target)
        if executable is None:
            return f"I couldn't find the approved app {name}."
        if Path(executable).suffix.casefold() not in {".exe", ".com"}:
            return f"The approved target for {name} must be a direct Windows executable."
        try:
            self._start_process([executable], shell=False)
        except Exception:
            return f"I couldn't open {name}."
        return f"Opening {name}."

    def create_folder(self, name: str) -> str:
        requested = Path(name.strip())
        if not name.strip():
            return "Tell me the name of the folder to create."
        if requested.is_absolute() or ".." in requested.parts:
            return "That folder path is outside the workspace, so I didn't create it."

        destination = (self.workspace / requested).resolve()
        try:
            destination.relative_to(self.workspace)
        except ValueError:
            return "That folder path is outside the workspace, so I didn't create it."
        try:
            destination.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            return "That folder already exists."
        except OSError:
            return "I couldn't create that folder inside the workspace."
        return f"Created folder {requested.as_posix()}."

    def search_web(self, query: str, browser: str = "default") -> str:
        query = query.strip()
        browser_key = browser.strip().casefold()
        if not query:
            return "Tell me what you want me to search for."
        if browser_key not in _BROWSERS:
            return "Choose the default browser, Chrome, Edge, or Firefox."
        url = f"https://www.google.com/search?q={quote_plus(query)}"
        try:
            controller = self._browser_get(None if browser_key == "default" else browser_key)
            opened = bool(controller.open_new_tab(url))
        except Exception:
            opened = False
        return "Opening the search in your browser." if opened else "I couldn't open the browser."
