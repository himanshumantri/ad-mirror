"""Exploratory capability checks against the Meta Model API using the clips in testdata/.

    python scripts/smoke_checks.py sam   "Clip A.mp4" "microwave"
    python scripts/smoke_checks.py voice "Clip A.mp4"
    python scripts/smoke_checks.py spark "Clip D.mp4"

Raw model output is saved to testdata/out/ so the formats can be inspected before parsers are written.
Docs: https://dev.meta.ai/docs/ (sam/segmenting, speech-to-text, image-understanding).
"""
import base64
import csv
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import httpx

BASE_URL = os.environ.get("META_API_BASE_URL", "https://api.meta.ai/v1").rstrip("/")
SAM_MODEL = os.environ.get("SAM_MODEL_ID", "sam-3.1")
SPARK_MODEL = os.environ.get("SPARK_MODEL_ID", "muse-spark-1.3")
VOICE_MODEL = os.environ.get("VOICE_MODEL_ID", "muse-voice-transcribe-1.0")

ROOT = Path(__file__).resolve().parents[2]
TESTDATA = ROOT / "testdata"
OUT = TESTDATA / "out"


def headers() -> dict:
    key = os.environ.get("MODEL_API_KEY")
    if not key:
        sys.exit("Set MODEL_API_KEY first.")
    return {"Authorization": f"Bearer {key}"}


def save(name: str, text: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(text, encoding="utf-8")
    print(f"saved testdata/out/{name} ({len(text)} chars)")


def output_text(response_json: dict) -> str:
    parts = []
    for item in response_json.get("output", []):
        for block in item.get("content", []) or []:
            if block.get("type") == "output_text":
                parts.append(block.get("text", ""))
    return "".join(parts)


def sam(clip: str, phrase: str) -> None:
    """Upload the clip, then ask SAM 3.1 for every instance of `phrase` tracked across frames."""
    path = TESTDATA / clip
    with path.open("rb") as fh:
        up = httpx.post(
            f"{BASE_URL}/files",
            headers=headers(),
            files={"file": (path.name, fh, "video/mp4")},
            data={"purpose": "user_data"},
            timeout=300,
        )
    print("upload ->", up.status_code)
    if up.status_code != 200:
        sys.exit(up.text[:500])
    file_id = up.json()["id"]

    body = {
        "model": SAM_MODEL,
        "input": [
            {
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "input_text", "text": phrase},
                    {"type": "input_video", "file_id": file_id},
                ],
            }
        ],
        "metadata": {"include_confidence": "true", "mask_encoding": "one_bit"},
        "stream": True,
    }
    text = []
    seen: dict[str, int] = {}
    completed = None
    with httpx.stream("POST", f"{BASE_URL}/responses", headers=headers(), json=body, timeout=600) as resp:
        print("responses ->", resp.status_code)
        if resp.status_code != 200:
            sys.exit(resp.read().decode()[:500])
        for line in resp.iter_lines():
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if not payload or payload == "[DONE]":
                continue
            event = json.loads(payload)
            kind = event.get("type", "?")
            seen[kind] = seen.get(kind, 0) + 1
            if kind == "response.output_text.delta":
                text.append(event["delta"])
            elif kind == "response.completed":
                completed = event
    print("events seen:", seen)
    if completed is not None:
        save(f"sam_{Path(clip).stem}_completed.json", json.dumps(completed, indent=2)[:20000])
    raw = "".join(text)
    save(f"sam_{Path(clip).stem}_{phrase.replace(' ', '_')}.txt", raw)
    lines = [ln for ln in raw.splitlines() if ln.strip()]
    print(f"{len(lines)} output lines; box tokens: {raw.count('|box')}")
    print("first line (truncated):", lines[0][:400] if lines else "(empty: no matches)")


def wav_from(clip: str) -> bytes:
    """Mono 16-bit 16 kHz WAV, as the file endpoint requires."""
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "audio.wav"
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-i", str(TESTDATA / clip), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)],
            check=True,
        )
        return wav.read_bytes()


def item_keywords() -> list[str]:
    with (TESTDATA / "book_stock.csv").open(newline="") as fh:
        return sorted({row["item"] for row in csv.DictReader(fh)})


def voice(clip: str) -> None:
    """Transcribe narration with item names as keyword bias; turn-level timestamps only."""
    req = {
        "model": VOICE_MODEL,
        "audioEncoding": "WAV",
        "mode": "ENDPOINTING",
        "keywords": item_keywords(),
        "languageBias": ["English"],
    }
    resp = httpx.post(
        f"{BASE_URL}/asr/transcribe",
        headers={**headers(), "Accept": "application/json"},
        files={"request": (None, json.dumps(req), "application/json"), "audio": ("audio.wav", wav_from(clip), "audio/wav")},
        timeout=300,
    )
    print("transcribe ->", resp.status_code)
    if resp.status_code != 200:
        sys.exit(resp.text[:500])
    data = resp.json()
    save(f"voice_{Path(clip).stem}.json", json.dumps(data, indent=2))
    print("keywords:", req["keywords"])
    print("transcript:", data.get("transcript"))
    for turn in data.get("turns", []):
        print(f"  {turn['startMs']}-{turn['endMs']} ms: {turn['transcript']}")


def frames_from(clip: str, count: int = 3) -> list[bytes]:
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(TESTDATA / clip)],
        check=True, capture_output=True, text=True,
    )
    duration = float(probe.stdout)
    frames = []
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(count):
            out = Path(tmp) / f"f{i}.jpg"
            t = duration * (i + 1) / (count + 1)
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(TESTDATA / clip), "-frames:v", "1", str(out)], check=True)
            frames.append(out.read_bytes())
    return frames


def spark(clip: str) -> None:
    """Ask Muse Spark 1.3 to identify items and read any label text in sampled frames."""
    content = [
        {
            "type": "input_text",
            "text": "These are frames from a stockroom shelf video. List every distinct item type you can see, "
            "how many of each are visible, and quote any label, brand or model text you can read exactly. "
            "Say 'unreadable' where text is not legible. Reply as JSON.",
        }
    ]
    for frame in frames_from(clip):
        content.append({"type": "input_image", "image_url": "data:image/jpeg;base64," + base64.b64encode(frame).decode()})
    body = {"model": SPARK_MODEL, "input": [{"type": "message", "role": "user", "content": content}]}
    resp = httpx.post(f"{BASE_URL}/responses", headers=headers(), json=body, timeout=300)
    print("spark ->", resp.status_code)
    if resp.status_code != 200:
        sys.exit(resp.text[:500])
    text = output_text(resp.json())
    save(f"spark_{Path(clip).stem}.txt", text)
    print(text[:1500])


def main() -> None:
    args = sys.argv[1:]
    if len(args) >= 3 and args[0] == "sam":
        sam(args[1], args[2])
    elif len(args) >= 2 and args[0] == "voice":
        voice(args[1])
    elif len(args) >= 2 and args[0] == "spark":
        spark(args[1])
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
