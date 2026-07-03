"""Microphone capture to 16 kHz mono WAV (kept in memory until stop; ~2 MB/min)."""

from __future__ import annotations

import wave
from pathlib import Path

SAMPLE_RATE = 16_000


class AudioRecorder:
    def __init__(self, path: Path):
        self._path = path
        self._chunks: list[bytes] = []
        self._stream = None

    def start(self) -> None:
        import sounddevice as sd

        def callback(indata, frames, time_info, status):
            self._chunks.append(bytes(indata))

        self._stream = sd.RawInputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="int16", callback=callback
        )
        self._stream.start()

    def stop(self) -> Path:
        if self._stream:
            self._stream.stop()
            self._stream.close()
        with wave.open(str(self._path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(b"".join(self._chunks))
        return self._path
