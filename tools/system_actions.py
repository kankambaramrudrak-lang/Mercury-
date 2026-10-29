"""Explicitly allowlisted package installation and safe workspace trashing."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable, Sequence


class SystemActions:
    """Install selected winget packages or move workspace items to Recycle Bin."""

    def __init__(
        self,
        workspace: str | Path,
        install_whitelist: Sequence[str] = (),
        *,
        run_command: Callable[..., object] | None = None,
        send_to_trash: Callable[[str], object] | None = None,
    ) -> None:
        self.workspace = Path(workspace).resolve()
        self._packages = {package.casefold(): package for package in install_whitelist}
        self._run_command = subprocess.run if run_command is None else run_command
        self._send_to_trash = send_to_trash

    def install_command(self, package_id: str) -> list[str] | None:
        approved_id = self._packages.get(package_id.strip().casefold())
        if approved_id is None:
            return None
        return [
            "winget",
            "install",
            "--id",
            approved_id,
            "--exact",
            "--source",
            "winget",
            "--accept-source-agreements",
            "--accept-package-agreements",
        ]

    def install_confirmation(self, package_id: str) -> str:
        command = self.install_command(package_id)
        if command is None:
            return f"Package {package_id} is not on the approved install list. No command will run."
        return (
            f"Install package {self._packages[package_id.strip().casefold()]}?\n"
            f"Exact command: {' '.join(command)}\n"
            "The installer may request Windows approval."
        )

    def install_app(self, package_id: str) -> str:
        command = self.install_command(package_id)
        if command is None:
            return f"Package {package_id} is not on the approved install list. Nothing was installed."
        try:
            result = self._run_command(command, shell=False, check=False, timeout=600)
        except Exception:
            return "The approved package installation could not be started."
        return "Installation completed." if getattr(result, "returncode", 1) == 0 else "The package installer reported a failure."

    def _safe_target(self, relative_path: str) -> Path | None:
        requested = Path(relative_path.strip())
        if not relative_path.strip() or requested.is_absolute() or ".." in requested.parts:
            return None
        target = self.workspace / requested
        try:
            resolved = target.resolve(strict=True)
            resolved.relative_to(self.workspace)
        except (OSError, ValueError):
            return None
        if resolved == self.workspace or target.is_symlink():
            return None
        return resolved

    def item_count(self, relative_path: str) -> int | None:
        target = self._safe_target(relative_path)
        if target is None:
            return None
        if not target.is_dir():
            return 1
        # Count the selected folder itself and each child, without traversing symlinks.
        return 1 + sum(1 for child in target.rglob("*") if not child.is_symlink()) + sum(
            1 for child in target.rglob("*") if child.is_symlink()
        )

    def delete_confirmation(self, relative_path: str) -> str:
        target = self._safe_target(relative_path)
        if target is None:
            return "That item is missing or outside the workspace. Nothing will be moved."
        count = self.item_count(relative_path)
        return f"Move this item to the Recycle Bin?\nFull path: {target}\nItems including this item: {count}"

    def delete_path(self, relative_path: str) -> str:
        target = self._safe_target(relative_path)
        if target is None:
            return "That item is missing or outside the workspace. Nothing was moved."
        if self._send_to_trash is None:
            try:
                from send2trash import send2trash
            except ImportError:
                return "Recycle Bin support is unavailable. Nothing was moved."
            send_to_trash = send2trash
        else:
            send_to_trash = self._send_to_trash
        try:
            send_to_trash(str(target))
        except Exception:
            return "I couldn't move that item to the Recycle Bin."
        return f"Moved {target.name} to the Recycle Bin."

\n