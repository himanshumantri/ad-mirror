"""Can SAM 3.1 on the hosted API take a still image, and box or point prompts, the way an auditor's "investigate this
variance" screen would need?

    python scripts/sam_still_test.py [--dry-run]

Uses frame 0 of Fresh 3 and Fresh 5 (the clips where dark cartons had no box). Each test asks SAM for objects on the
still and prints what came back. Raw output is saved as testdata/out/sam_still_<label>.txt. --dry-run extracts the
frames and prints the requests without calling the API (no key needed).

Request format is from the SAM "segmenting" docs: an input_text part holding either a noun phrase or box/point
tokens, plus an input_image part. Box and point prompts use up to 16 objects and cannot be mixed with a phrase.
"""
import argparse
import base64
import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import BASE_URL, OUT, SAM_MODEL, TESTDATA, auth_headers  # noqa: E402
from app.media import extract_frame  # noqa: E402
from app.segmentation import parse_sam_output  # noqa: E402

# Spark's own boxes for the cartons SAM missed, in pixels of the 576x1024 frame (from the cached verification).
BOXES = {
    "Fresh 5": [[330, 435, 525, 540], [330, 542, 517, 587], [330, 590, 517, 630], [330, 632, 517, 672]],  # four black keyboard cartons
    "Fresh 3": [[119, 168, 519, 280], [78, 209, 282, 360]],  # black keyboard carton, small red carton
}


def tokens_box(boxes: list[list[int]], w: int, h: int) -> str:
    return "<0f>" + ",".join(f"{i}<|box;x1={x1};y1={y1};x2={x2};y2={y2};w={w};h={h}|>" for i, (x1, y1, x2, y2) in enumerate(boxes, 1))


def tokens_point(boxes: list[list[int]], w: int, h: int) -> str:
    """One positive point at the centre of each box."""
    return "<0f>" + ",".join(f"{i}<|point;x={(x1 + x2) // 2};y={(y1 + y2) // 2};w={w};h={h}|>" for i, (x1, y1, x2, y2) in enumerate(boxes, 1))


def ask(text: str, image: Path) -> tuple[int, str]:
    data_url = "data:image/png;base64," + base64.b64encode(image.read_bytes()).decode()
    body = {
        "model": SAM_MODEL,
        "input": [{"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": text},
            {"type": "input_image", "image_url": data_url},
        ]}],
        "metadata": {"include_confidence": "true", "mask_encoding": "one_bit"},
        "stream": True,
    }
    deltas: list[str] = []
    with httpx.stream("POST", f"{BASE_URL}/responses", headers=auth_headers(), json=body, timeout=300) as resp:
        if resp.status_code != 200:
            return resp.status_code, resp.read().decode()[:600]
        for line in resp.iter_lines():
            if line.startswith("data:") and line[5:].strip() not in ("", "[DONE]"):
                event = json.loads(line[5:])
                if event.get("type") == "response.output_text.delta":
                    deltas.append(event["delta"])
    return 200, "".join(deltas)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    for clip, boxes in BOXES.items():
        still = OUT / "stills" / f"{clip}_f0.png"
        extract_frame(TESTDATA / f"{clip}.mp4", 0, still)
        from PIL import Image

        w, h = Image.open(still).size
        tests = {
            "text cardboard box": "cardboard box",
            "text keyboard box": "keyboard box",
            "box prompts": tokens_box(boxes, w, h),
            "point prompts": tokens_point(boxes, w, h),
        }
        print(f"\n== {clip}: still is {w}x{h}, {len(boxes)} missed cartons prompted")
        for label, text in tests.items():
            name = f"{clip}_{label}".replace(" ", "_")
            print(f"-- {label}: {text[:110]}{'...' if len(text) > 110 else ''}")
            if args.dry_run:
                continue
            status, raw = ask(text, still)
            (OUT / f"sam_still_{name}.txt").write_text(raw, encoding="utf-8")
            if status != 200:
                print(f"   FAILED {status}: {raw}")
                continue
            found = parse_sam_output(raw).get(0, [])
            print(f"   ok: {len(found)} object(s) with boxes; confidences {[round(d.conf, 2) for d in found]}")
            for d in found:
                print(f"   id {d.obj_id}: box ({d.x1},{d.y1})-({d.x2},{d.y2})")
            if not found:
                print(f"   raw output head: {raw[:200]!r}")


if __name__ == "__main__":
    main()
