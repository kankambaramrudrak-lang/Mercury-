"""Hercules Milestone 1: local push-to-talk greeting prototype."""

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
from pathlib import Path


MODEL_PATH = Path(__file__).parent / "model" / "vosk-model-small-en-us-0.15"
SAMPLE_RATE = 16_000


def reply_for(text: str) -> str:
    """Return a deterministic reply for a recognized greeting."""
    normalized = text.strip().lower().strip(".,!? ")
    if re.search(r"\b(hello|hi|hey|good morning|good afternoon|good evening)\b", normalized):
        return "Hello! I'm Hercules."
    return "I heard you, but this first version only knows simple greetings."


def run() -> int:
    parser = argparse.ArgumentParser(description="Local push-to-talk voice greeting demo")
    parser.add_argument("--list-devices", action="store_true", help="list audio devices and exit")
    args = parser.parse_args()

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
    engine = pyttsx3.init("sapi5")

    holding = threading.Event()
    released = threading.Event()
    recording: list[bytes] = []
    recording_lock = threading.Lock()

    def on_press(key: object) -> None:
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

    def audio_callback(indata: object, frames: int, time_info: object, status: object) -> None:
        if status:
            print(f"Audio device status: {status}", file=sys.stderr)
        if holding.is_set():
            with recording_lock:
                recording.append(bytes(indata))

    print("Hercules is ready. Hold Right Ctrl, say hello, then release it. Press Esc to quit.")
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
                            print("No audio captured. Hold Right Ctrl while speaking and try again.")
                            continue
                        recognizer = KaldiRecognizer(model, SAMPLE_RATE)
                        recognizer.AcceptWaveform(audio)
                        recognized = json.loads(recognizer.FinalResult()).get("text", "")
                        if not recognized:
                            print("I didn't catch that. Try again.")
                            continue
                        # Do not print or save recognized speech; respond locally.
                        engine.say(reply_for(recognized))
                        engine.runAndWait()
                return 0
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        print(f"Could not start the microphone or speech output: {exc}", file=sys.stderr)
        print("Try `python main.py --list-devices` and check Windows microphone permissions.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(run())
