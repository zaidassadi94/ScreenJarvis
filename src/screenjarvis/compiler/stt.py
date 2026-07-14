"""Speech-to-text with word-level timestamps.

Word timing is a hard requirement: aligning "look at *this*" to a cursor
position is the whole trick. Backends:

- openai  — whisper-1 via /audio/transcriptions
- groq    — whisper-large-v3-turbo via the same OpenAI-compatible endpoint
- json    — reuse an existing raw/transcript.json (recompiles, tests)

Key routing is forgiving: a key is sent to the service its prefix names
(`gsk_` → Groq, `sk-` → OpenAI), even if it was pasted into the other slot, so
a first-time user can't silently misconfigure themselves into 401s.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

_ENDPOINTS = {
    "groq": {"base": "https://api.groq.com/openai/v1", "env": "GROQ_API_KEY",
             "model": "whisper-large-v3-turbo", "prefix": "gsk_"},
    "openai": {"base": "https://api.openai.com/v1", "env": "OPENAI_API_KEY",
               "model": "whisper-1", "prefix": "sk-"},
}
BACKENDS = ("groq", "openai")  # auto order: Groq first (fast + cheap)


def _available_keys() -> list[str]:
    return [v for v in (os.environ.get(ep["env"], "") for ep in _ENDPOINTS.values()) if v]


def resolve_backend(preference: str) -> tuple[str, str]:
    """Pick (backend_name, api_key).

    Prefers a key whose prefix matches a candidate service, so a Groq key
    pasted into the OpenAI slot (or vice versa) still transcribes. Falls back
    to the chosen service's own slot key when no prefix matches.
    """
    order = [preference] if preference in _ENDPOINTS else list(BACKENDS)
    keys = _available_keys()
    for name in order:  # route by key format first
        prefix = _ENDPOINTS[name]["prefix"]
        for key in keys:
            if key.startswith(prefix):
                return name, key
    for name in order:  # otherwise use the service's own slot, whatever it holds
        if key := os.environ.get(_ENDPOINTS[name]["env"], ""):
            return name, key
    raise SystemExit(
        "No speech-to-text key found. Run `sj setup` and paste an OpenAI or Groq "
        "API key (Groq keys start with gsk_, OpenAI with sk-)."
    )


def pick_backend(preference: str) -> str:
    return resolve_backend(preference)[0]


def transcribe(audio: Path, preference: str) -> dict:
    name, key = resolve_backend(preference)
    ep = _ENDPOINTS[name]
    import httpx

    with open(audio, "rb") as f:
        response = httpx.post(
            f"{ep['base']}/audio/transcriptions",
            headers={"Authorization": f"Bearer {key}"},
            files={"file": (audio.name, f, "audio/wav")},
            data={
                "model": ep["model"],
                "response_format": "verbose_json",
                "timestamp_granularities[]": ["word", "segment"],
            },
            timeout=httpx.Timeout(180, connect=15),
        )
    if response.status_code != 200:
        detail = response.text[:300]
        if response.status_code == 401:
            detail += (f"  →  {name.capitalize()} rejected the key. Check the {name} key "
                       f"you saved with `sj setup` is correct and still active in the "
                       f"{name.capitalize()} console.")
        raise SystemExit(f"{name} transcription failed ({response.status_code}): {detail}")
    return normalize(response.json())


def normalize(raw: dict) -> dict:
    words = [
        {"word": str(w["word"]).strip(), "start": float(w["start"]), "end": float(w["end"])}
        for w in raw.get("words") or []
    ]
    if not words:
        raise SystemExit("The transcription came back with no word timestamps; ScreenJarvis needs word-level timing.")
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
