"""Console loop for entering commands without audio hardware."""

from __future__ import annotations

from collections.abc import Callable

from core.router import CommandRouter


def run_text_mode(
    router: CommandRouter,
    input_fn: Callable[[str], str] | None = None,
    output_fn: Callable[[str], None] | None = None,
) -> None:
    """Read commands until the user types exit or quit."""
    input_fn = input if input_fn is None else input_fn
    output_fn = print if output_fn is None else output_fn
    output_fn("Text mode: enter a command, or type 'exit' to quit.")
    while True:
        try:
            text = input_fn("> ")
        except EOFError:
            output_fn("Goodbye.")
            return
        if text.strip().lower() in {"exit", "quit"}:
            output_fn("Goodbye.")
            return
        output_fn(router.handle(text))
