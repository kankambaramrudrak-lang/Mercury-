"""Console loop for entering commands without audio hardware."""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable

from core.router import CommandRouter


def run_text_mode(
    router: CommandRouter,
    input_fn: Callable[[str], str] | None = None,
    output_fn: Callable[[str], None] | None = None,
    on_tick: Callable[[], None] | None = None,
) -> None:
    """Read commands until the user types exit or quit."""
    input_fn = input if input_fn is None else input_fn
    output_fn = print if output_fn is None else output_fn
    output_fn("Text mode: enter a command, or type 'exit' to quit.")
    while True:
        result: queue.Queue[tuple[str, str | Exception]] = queue.Queue(maxsize=1)

        def read_input() -> None:
            try:
                result.put(("text", input_fn("> ")))
            except EOFError:
                result.put(("eof", ""))
            except Exception as error:
                result.put(("error", error))

        threading.Thread(target=read_input, name="hercules-console-input", daemon=True).start()
        while True:
            if on_tick is not None:
                on_tick()
            try:
                kind, text = result.get(timeout=0.1)
                break
            except queue.Empty:
                time.sleep(0.01)
        if kind == "eof":
            output_fn("Goodbye.")
            return
        if kind == "error":
            assert isinstance(text, Exception)
            raise text
        assert isinstance(text, str)
        if text.strip().lower() in {"exit", "quit"}:
            output_fn("Goodbye.")
            return
        output_fn(router.handle(text))
