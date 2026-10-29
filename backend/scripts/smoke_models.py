"""List the model IDs the Meta Model API key can see (OpenAI-compatible GET /models)."""
import os
import sys

import httpx

# Base URL and key variable name per https://dev.meta.ai/docs/
BASE_URL = os.environ.get("META_API_BASE_URL", "https://api.meta.ai/v1").rstrip("/")


def main() -> int:
    key = os.environ.get("MODEL_API_KEY")
    if not key:
        print("Set MODEL_API_KEY first.", file=sys.stderr)
        return 1

    resp = httpx.get(f"{BASE_URL}/models", headers={"Authorization": f"Bearer {key}"}, timeout=30)
    print(f"GET {BASE_URL}/models -> {resp.status_code}")
    if resp.status_code != 200:
        print(resp.text[:500], file=sys.stderr)
        return 1

    ids = sorted(m.get("id", "") for m in resp.json().get("data", []))
    for model_id in ids:
        print(model_id)

    expected = {
        "segmenter (SAM 3.1)": os.environ.get("SAM_MODEL_ID", "sam-3.1"),
        "reader (Muse Spark)": os.environ.get("SPARK_MODEL_ID", "muse-spark-1.3"),
        "transcriber (Muse Voice Transcribe)": os.environ.get("VOICE_MODEL_ID", "muse-voice-transcribe-1.0"),
    }
    print("\nExpected models:")
    missing = 0
    for role, model_id in expected.items():
        found = model_id in ids
        missing += not found
        print(f"  [{'ok' if found else 'MISSING'}] {role}: {model_id}")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
