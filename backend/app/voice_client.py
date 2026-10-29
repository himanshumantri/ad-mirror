"""Muse Voice Transcribe over the Meta Model API: staff narration to turn-level text."""
import json
from pathlib import Path

import httpx

from app.config import BASE_URL, OUT, VOICE_MODEL, auth_headers
from app.media import wav_bytes


def transcribe(video: Path, keywords: list[str], language: str = "English") -> dict:
    """TranscribeResponse as a dict (`transcript`, `turns` with startMs/endMs). Cached by clip."""
    cache = OUT / f"voice_{video.stem}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))

    req = {"model": VOICE_MODEL, "audioEncoding": "WAV", "mode": "ENDPOINTING", "keywords": keywords, "languageBias": [language]}
    resp = httpx.post(
        f"{BASE_URL}/asr/transcribe",
        headers={**auth_headers(), "Accept": "application/json"},
        files={"request": (None, json.dumps(req), "application/json"), "audio": ("audio.wav", wav_bytes(video), "audio/wav")},
        timeout=300,
    )
    resp.raise_for_status()
    data = resp.json()
    OUT.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data
