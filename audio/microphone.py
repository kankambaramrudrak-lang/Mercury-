"""Push-to-talk microphone capture for the local voice mode."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import TYPE_CHECKING

from core.confirm import process_pending_confirmations

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray


SAMPLE_RATE = 16_000


class PushToTalkMicrophone:
    """Capture mono 16 kHz audio while Right Ctrl is held."""

    def run(self, on_audio: Callable[[bytes], None]) -> None:
        import sounddevice as sd
        from pynput import keyboard

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
            return None

        def on_release(key: object) -> None:
            if key == keyboard.Key.ctrl_r and holding.is_set():
                holding.clear()
                released.set()

        def audio_callback(
            indata: NDArray[np.int16],
            frames: int,
            time_info: object,
            status: object,
        ) -> None:
            if status:
                print(f"Audio device status: {status}")
            if holding.is_set():
                with recording_lock:
                    recording.append(indata.tobytes())

        print("Hercules is ready. Hold Right Ctrl to speak. Press Esc to quit.")
        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="int16",
            callback=audio_callback,
        ):
            with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
                while listener.running:
                    time.sleep(0.05)
                    process_pending_confirmations()
                    if released.is_set():
                        released.clear()
                        with recording_lock:
                            audio = b"".join(recording)
                            recording.clear()
                        on_audio(audio)


def list_audio_devices() -> None:
    """Print available devices without starting microphone capture."""
    import sounddevice as sd

    print(sd.query_devices())
