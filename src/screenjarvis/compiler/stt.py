"""Speech-to-text with word-level timestamps.

Word timing is a hard requirement: aligning "look at *this*" to a cursor
position is the whole trick. Backends:

- openai  — whisper-1 via /audio/transcriptions
- groq    — whisper-large-v3-turbo via the same OpenAI-compatible endpoint
- json    — reuse an existing raw/transcript.json (recompiles, tests)
"""

from __future__ import annotations

import json
import os
from pathlib import Path

BACKENDS = ("openai", "groq")
_ENDPOINTS = {
    "openai": ("https://api.openai.com/v1", "OPENAI_API_KEY", "whisper-1"),
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY", "whisper-large-v3-turbo"),
}


def pick_backend(preference: str) -> str:
    if preference in _ENDPOINTS:
        return preference
    for name in BACKENDS:
        if os.environ.get(_ENDPOINTS[name][1]):
            return name
    raise SystemExit(
        "No STT backend available: set OPENAI_API_KEY or GROQ_API_KEY "
        "(or pass --stt json to reuse an existing raw/transcript.json)."
    )


def transcribe(audio: Path, backend: str) -> dict:
    base, key_env, model = _ENDPOINTS[backend]
    key = os.environ.get(key_env)
    if not key:
        raise SystemExit(f"{key_env} is not set (required for --stt {backend}).")
    import httpx

    with open(audio, "rb") as f:
        response = httpx.post(
            f"{base}/audio/transcriptions",
            headers={"Authorization": f"Bearer {key}"},
            files={"file": (audio.name, f, "audio/wav")},
            data={
                "model": model,
                "response_format": "verbose_json",
                "timestamp_granularities[]": ["word", "segment"],
            },
            timeout=httpx.Timeout(180, connect=15),
        )
    if response.status_code != 200:
        raise SystemExit(f"STT request failed ({response.status_code}): {response.text[:400]}")
    return normalize(response.json())


def normalize(raw: dict) -> dict:
    words = [
        {"word": str(w["word"]).strip(), "start": float(w["start"]), "end": float(w["end"])}
        for w in raw.get("words") or []
    ]
    if not words:
        raise SystemExit("STT backend returned no word timestamps; ScreenJarvis needs word-level timing.")
    segments = [
        {"start": float(s["start"]), "end": float(s["end"]), "text": str(s["text"]).strip()}
        for s in raw.get("segments") or []
    ]
    if not segments:
        segments = [{"start": words[0]["start"], "end": words[-1]["end"],
                     "text": str(raw.get("text", "")).strip()}]
    return {
        "text": str(raw.get("text", "")).strip(),
        "language": raw.get("language"),
        "duration": float(raw.get("duration") or words[-1]["end"]),
        "segments": segments,
        "words": words,
    }


def load_transcript(path: Path) -> dict:
    return json.loads(path.read_text())
