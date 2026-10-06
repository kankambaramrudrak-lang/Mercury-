"""Hercules Milestone 1: local push-to-talk greeting prototype."""

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast

from tasks import TaskCommands, TaskStore

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray

MODEL_PATH = Path(__file__).parent / "model" / "vosk-model-small-en-us-0.15"
DATABASE_PATH = Path(__file__).parent / "data" / "hercules.sqlite3"
SAMPLE_RATE = 16_000
TEST_SPEECH_TEXT = "This is a Hercules speech output test."


class SpeechEngine(Protocol):
    def say(self, text: str | None, name: str | None = None) -> str | None: ...

    def runAndWait(self) -> None: ...


def reply_for(text: str, task_commands: TaskCommands | None = None) -> str:
    """Return a local task response, greeting, or clarification."""
    task_response = task_commands.handle(text) if task_commands is not None else None
    if task_response is not None:
        return task_response
    normalized = text.strip().lower().strip(".,!? ")
    if re.search(r"\b(hello|hi|hey|good morning|good afternoon|good evening)\b", normalized):
        return "Hello! I'm Hercules."
    return (
        "I didn't understand. Say 'Add task' followed by a description, "
        "'List tasks', 'Complete task' followed by a number, 'Update task' "
        "followed by a number and new description, or 'Delete task' followed by a number."
    )


def speak_response(engine: SpeechEngine, text: str) -> None:
    """Print a reply once, then speak that exact reply."""
    print(text, flush=True)
    engine.say(text)
    engine.runAndWait()


def report_recognition(text: str, debug: bool) -> None:
    """Display recognized words only when the user explicitly enables debug mode."""
    if debug:
        print(f"Recognized words: {text}", flush=True)


def run() -> int:
    parser = argparse.ArgumentParser(description="Local push-to-talk voice greeting demo")
    parser.add_argument("--list-devices", action="store_true", help="list audio devices and exit")
    parser.add_argument(
        "--debug-recognition",
        action="store_true",
        help="print recognized words locally (speech is not saved)",
    )
    parser.add_argument(
        "--test-speech",
        action="store_true",
        help="speak a fixed test sentence without opening the microphone",
    )
    args = parser.parse_args()

    if args.test_speech:
        try:
            import pyttsx3
        except ImportError as exc:
            print(f"Missing dependency: {exc}. Activate .venv and install requirements.txt.", file=sys.stderr)
            return 1
        engine = cast(SpeechEngine, pyttsx3.init("sapi5"))
        speak_response(engine, TEST_SPEECH_TEXT)
        return 0

    try:
        import sounddevice as sd
        if args.list_devices:
            print(sd.query_devices())
            return 0

        from pynput import keyboard
        import pyttsx3
        from vosk import KaldiRecognizer, Model
    except ImportError as exc:
        print(f"Missing dependency: {exc}. Activate .venv and install requirements.txt.", file=sys.stderr)
        return 1

    if not MODEL_PATH.is_dir():
        print(f"Speech model not found: {MODEL_PATH}\nFollow the model setup steps in README.md.", file=sys.stderr)
        return 1

    print("Loading the local speech model…")
    model = Model(str(MODEL_PATH))
    engine = cast(SpeechEngine, pyttsx3.init("sapi5"))
    task_store = TaskStore(DATABASE_PATH)
    task_commands = TaskCommands(task_store)

    holding = threading.Event()
    released = threading.Event()
    recording: list[bytes] = []
    recording_lock = threading.Lock()

    def on_press(key: object) -> bool | None:
        if key == keyboard.Key.esc:
            return False
        if key == keyboard.Key.ctrl_r and not holding.is_set():
            with recording_lock:
                recording.clear()
            released.clear()
            holding.set()
            print("Listening… release Right Ctrl when you finish.")

    def on_release(key: object) -> None:
        if key == keyboard.Key.ctrl_r and holding.is_set():
            holding.clear()
            released.set()

    def audio_callback(indata: NDArray[np.int16], frames: int, time_info: object, status: object) -> None:
        if status:
            print(f"Audio device status: {status}", file=sys.stderr)
        if holding.is_set():
            with recording_lock:
                recording.append(indata.tobytes())

    print("Hercules is ready. Hold Right Ctrl to speak. Press Esc to quit.")
    try:
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", callback=audio_callback):
            with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
                while listener.running:
                    time.sleep(0.05)

                    if released.is_set():
                        released.clear()
                        with recording_lock:
                            audio = b"".join(recording)
                            recording.clear()
                        if not audio:
                            if task_commands.cancel_pending_deletion():
                                message = "I didn't catch the confirmation. Deletion canceled; nothing was deleted."
                            else:
                                message = "No audio captured. Hold Right Ctrl while speaking and try again."
                            speak_response(engine, message)
                            continue
                        recognizer = KaldiRecognizer(model, SAMPLE_RATE)
                        recognizer.AcceptWaveform(audio)
                        recognized = json.loads(recognizer.FinalResult()).get("text", "")
                        if not recognized:
                            if task_commands.cancel_pending_deletion():
                                message = "I didn't catch the confirmation. Deletion canceled; nothing was deleted."
                            else:
                                message = "I didn't catch that. Please repeat your command."
                            speak_response(engine, message)
                            continue
                        report_recognition(recognized, args.debug_recognition)
                        # Do not print or save recognized speech; respond locally.
                        speak_response(engine, reply_for(recognized, task_commands))
                return 0
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        print(f"Could not start the microphone or speech output: {exc}", file=sys.stderr)
        print("Try `python main.py --list-devices` and check Windows microphone permissions.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(run())
