"""Automatic microphone capture with in-memory silence-based phrase detection."""

from __future__ import annotations

import queue
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from core.confirm import process_pending_confirmations

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray


SAMPLE_RATE = 16_000
_FRAME_SECONDS = 0.1
_FRAME_SAMPLES = int(SAMPLE_RATE * _FRAME_SECONDS)
_RMS_THRESHOLD = 450.0
_SILENCE_SECONDS = 0.75
_MIN_SPEECH_SECONDS = 0.25
_MAX_UTTERANCE_SECONDS = 12.0


class SilenceSegmenter:
    """Collect a short utterance until enough silence follows speech."""

    def __init__(
        self,
        sample_rate: int = SAMPLE_RATE,
        rms_threshold: float = _RMS_THRESHOLD,
        silence_seconds: float = _SILENCE_SECONDS,
        min_speech_seconds: float = _MIN_SPEECH_SECONDS,
        max_utterance_seconds: float = _MAX_UTTERANCE_SECONDS,
        pre_roll_frames: int = 3,
    ) -> None:
        self._bytes_per_second = sample_rate * 2  # mono signed 16-bit PCM
        self._rms_threshold = rms_threshold
        self._silence_seconds = silence_seconds
        self._min_speech_seconds = min_speech_seconds
        self._max_utterance_seconds = max_utterance_seconds
        self._pre_roll: deque[bytes] = deque(maxlen=pre_roll_frames)
        self._reset_utterance()

    def add_frame(self, frame: bytes, rms: float) -> bytes | None:
        """Add one PCM frame and return a complete utterance when ready."""
        duration = len(frame) / self._bytes_per_second
        if duration <= 0:
            return None

        if not self._active:
            self._pre_roll.append(frame)
            if rms < self._rms_threshold:
                return None
            self._active = True
            self._frames = list(self._pre_roll)
            self._utterance_seconds = sum(
                len(item) / self._bytes_per_second for item in self._frames
            )
            self._speech_seconds = duration
            self._quiet_seconds = 0.0
        else:
            self._frames.append(frame)
            self._pre_roll.append(frame)
            self._utterance_seconds += duration
            if rms >= self._rms_threshold:
                self._speech_seconds += duration
                self._quiet_seconds = 0.0
            else:
                self._quiet_seconds += duration

        if (
            self._quiet_seconds >= self._silence_seconds
            or self._utterance_seconds >= self._max_utterance_seconds
        ):
            utterance = b"".join(self._frames) if self._speech_seconds >= self._min_speech_seconds else None
            self._reset_utterance()
            return utterance
        return None

    def reset(self) -> None:
        """Discard any buffered audio, such as while Mercury is speaking."""
        self._pre_roll.clear()
        self._reset_utterance()

    def _reset_utterance(self) -> None:
        self._active = False
        self._frames: list[bytes] = []
        self._utterance_seconds = 0.0
        self._speech_seconds = 0.0
        self._quiet_seconds = 0.0


@dataclass(frozen=True)
class _AudioEvent:
    kind: Literal["audio", "status"]
    value: bytes | str


class AlwaysListeningMicrophone:
    """Keep the input stream open and send speech segments after a pause.

    Audio is buffered in memory only. The stream drops input while Mercury is
    speaking so its own replies are not mistaken for new commands.
    """

    def __init__(self, device: str | int | None = None) -> None:
        self._device = device

    def run(
        self,
        on_audio: Callable[[bytes], None],
        on_status: Callable[[str], None] = print,
        on_tick: Callable[[], None] | None = None,
    ) -> None:
        import numpy as np
        import sounddevice as sd
        from pynput import keyboard

        events: queue.Queue[_AudioEvent] = queue.Queue()
        processing = threading.Event()
        segmenter = SilenceSegmenter()

        def audio_callback(
            indata: NDArray[np.int16],
            frames: int,
            time_info: object,
            status: object,
        ) -> None:
            if status:
                events.put(_AudioEvent("status", f"Microphone status: {status}"))
            if processing.is_set():
                segmenter.reset()
                return

            frame = indata.tobytes()
            rms = float(np.sqrt(np.mean(indata.astype(np.float32) ** 2)))
            utterance = segmenter.add_frame(frame, rms)
            if utterance is not None:
                events.put(_AudioEvent("audio", utterance))

        def on_press(key: object) -> bool | None:
            if key == keyboard.Key.esc:
                return False
            return None

        # Speak this before opening the stream so the microphone cannot capture
        # Mercury's own startup announcement as a command.
        on_status("Mercury is ready and listening. Say a command. Press Esc to quit.")

        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="int16",
            blocksize=_FRAME_SAMPLES,
            callback=audio_callback,
            device=self._device,
        ):
            with keyboard.Listener(on_press=on_press) as listener:
                print("Listening…", flush=True)
                while listener.running:
                    process_pending_confirmations()
                    if on_tick is not None:
                        processing.set()
                        try:
                            on_tick()
                        finally:
                            processing.clear()
                    try:
                        event = events.get(timeout=0.05)
                    except queue.Empty:
                        time.sleep(0.01)
                        continue

                    processing.set()
                    try:
                        if event.kind == "status":
                            on_status(str(event.value))
                        else:
                            # Drop segments already queued before speech began.
                            while True:
                                try:
                                    events.get_nowait()
                                except queue.Empty:
                                    break
                            on_audio(bytes(event.value))
                    finally:
                        processing.clear()
                        if event.kind == "audio":
                            print("Listening…", flush=True)


def list_audio_devices() -> None:
    """Print available devices without starting microphone capture."""
    import sounddevice as sd

    print(sd.query_devices())
