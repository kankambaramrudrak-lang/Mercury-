"""Main-thread Tkinter confirmation with a safe worker-thread request queue."""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

CONFIRMATION_TIMEOUT_SECONDS = 30.0


@dataclass
class _Request:
    title: str
    details: str
    deadline: float
    completed: threading.Event = field(default_factory=threading.Event)
    approved: bool = False
    expired: bool = False


Presenter = Callable[[str, str, float], bool]


def _show_tk_confirmation(title: str, details: str, timeout: float) -> bool:
    """Show a modal prompt. This function is called only on the main thread."""
    deadline = time.monotonic() + max(0.0, timeout)
    import tkinter as tk

    # Use the Tk root itself as the visible dialog. A withdrawn root with a
    # child Toplevel can leave the confirmation hidden on Windows.
    dialog = tk.Tk()
    dialog.title(title)
    is_long = len(details) > 1_200
    dialog.resizable(is_long, is_long)

    decision = {"approved": False, "done": False}

    def finish(approved: bool) -> None:
        if decision["done"]:
            return
        decision["done"] = True
        if time.monotonic() < deadline:
            decision["approved"] = approved
        dialog.destroy()

    if is_long:
        from tkinter.scrolledtext import ScrolledText

        text_view = ScrolledText(dialog, width=96, height=26, wrap="word", padx=12, pady=10)
        text_view.insert("1.0", details)
        text_view.configure(state="disabled")
        text_view.pack(fill="both", expand=True, padx=10, pady=10)
        dialog.geometry("900x700")
    else:
        tk.Label(dialog, text=details, wraplength=520, justify="left", padx=18, pady=16).pack()
    buttons = tk.Frame(dialog, padx=12, pady=8)
    buttons.pack()
    approve = tk.Button(buttons, text="Approve", command=lambda: finish(True))
    approve.pack(side="left", padx=6)
    cancel = tk.Button(buttons, text="Cancel", command=lambda: finish(False), default="active")
    cancel.pack(side="left", padx=6)
    cancel.focus_set()
    dialog.bind("<Return>", lambda _event: finish(False))
    dialog.bind("<Escape>", lambda _event: finish(False))
    dialog.protocol("WM_DELETE_WINDOW", lambda: finish(False))
    remaining_ms = max(1, int((deadline - time.monotonic()) * 1000))
    dialog.after(remaining_ms, lambda: finish(False))
    dialog.grab_set()
    dialog.update_idletasks()
    dialog.deiconify()
    dialog.lift()
    dialog.focus_force()
    dialog.mainloop()
    return bool(decision["approved"])


class ConfirmationService:
    """Ask from any thread; all presentation happens on the main thread.

    The main application thread must call ``process_pending_requests`` while it
    runs. A worker request waits at most 30 seconds for its decision.
    """

    def __init__(
        self,
        presenter: Presenter = _show_tk_confirmation,
        timeout_seconds: float = CONFIRMATION_TIMEOUT_SECONDS,
    ) -> None:
        self._presenter = presenter
        self._timeout = timeout_seconds
        self._main_thread_id = threading.main_thread().ident
        self._requests: queue.Queue[_Request] = queue.Queue()

    def ask_confirmation(self, title: str, details: str) -> bool:
        request = _Request(title, details, time.monotonic() + self._timeout)
        if threading.get_ident() == self._main_thread_id:
            self._resolve(request)
            return request.approved

        self._requests.put(request)
        remaining = max(0.0, request.deadline - time.monotonic())
        if not request.completed.wait(remaining):
            request.expired = True
            return False
        return request.approved and time.monotonic() < request.deadline

    def process_pending_requests(self) -> None:
        """Present queued requests; call only from the main application thread."""
        if threading.get_ident() != self._main_thread_id:
            raise RuntimeError("Confirmation requests must be processed on the main thread")
        while True:
            try:
                request = self._requests.get_nowait()
            except queue.Empty:
                return
            self._resolve(request)

    def _resolve(self, request: _Request) -> None:
        remaining = request.deadline - time.monotonic()
        if request.expired or remaining <= 0:
            request.completed.set()
            return
        try:
            request.approved = bool(self._presenter(request.title, request.details, remaining))
        except Exception:
            # A broken or unavailable dialog must fail closed.
            request.approved = False
        if request.expired or time.monotonic() >= request.deadline:
            request.approved = False
        request.completed.set()


_default_service = ConfirmationService()


def ask_confirmation(title: str, details: str) -> bool:
    """Ask for button approval, refusing on cancellation or timeout."""
    return _default_service.ask_confirmation(title, details)


def process_pending_confirmations() -> None:
    """Service worker-thread requests from the app's main-thread event loop."""
    _default_service.process_pending_requests()
