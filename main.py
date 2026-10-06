"""Start Hercules and select its interaction mode."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from core.router import CommandRouter
from core.text_mode import run_text_mode
from tools.tasks import TaskCommands, TaskStore


DATABASE_PATH = Path(__file__).parent / "data" / "hercules.sqlite3"
TEST_SPEECH_TEXT = "This is a Hercules speech output test."


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local Hercules voice assistant")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--text", action="store_true", help="type commands instead of using the microphone")
    modes.add_argument("--test-speech", action="store_true", help="test the local Windows speech output")
    modes.add_argument("--list-devices", action="store_true", help="list audio devices and exit")
    args = parser.parse_args(argv)

    if args.list_devices:
        from audio.microphone import list_audio_devices

        list_audio_devices()
        return 0

    if args.test_speech:
        from audio.speech_output import SpeechOutput

        SpeechOutput().speak(TEST_SPEECH_TEXT)
        return 0

    router = CommandRouter(TaskCommands(TaskStore(DATABASE_PATH)))
    if args.text:
        run_text_mode(router)
        return 0

    from core.voice_mode import run_voice_mode

    run_voice_mode(router)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
