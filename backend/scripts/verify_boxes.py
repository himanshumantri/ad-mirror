"""Ask Muse Spark to check each SAM box on a clip's best frame, N times. Needs MODEL_API_KEY.

    python scripts/verify_boxes.py "Clip B.mp4" [runs]

Reads cached testdata/out/sam_<clip>_cardboard_box.txt (run smoke_checks.py sam first). Writes
testdata/out/verify_<clip>.json (every run) and verify_<clip>_review.png: the frame Spark saw with
green = SAM box Spark agrees with, orange = SAM box Spark disputes, blue ? = carton Spark says has no box.
"""
import base64
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.annotate import draw_boxes, draw_review  # noqa: E402
from app.segmentation import Filters, best_frame, filter_frame, parse_sam_output  # noqa: E402

BASE_URL = os.environ.get("META_API_BASE_URL", "https://api.meta.ai/v1").rstrip("/")
SPARK_MODEL = os.environ.get("SPARK_MODEL_ID", "muse-spark-1.3")
TESTDATA = Path(__file__).resolve().parents[2] / "testdata"
OUT = TESTDATA / "out"

# Loose on size so real small cartons survive; Spark decides what is a distinct, mostly visible carton.
LOOSE = Filters(min_area_frac=0.03)

PROMPT = """This frame comes from a stockroom video. A detector drew red numbered boxes; each box is supposed to \
outline one cardboard carton. For every numbered box answer:
- distinct_carton: true only if the box outlines exactly one carton (not a fragment of one, not two merged, not background).
- visible_fraction: "more_than_half" or "half_or_less" - how much of that carton is visible in the frame.
- label_text: legible printed or handwritten text on it, exactly as written, or "none".
Then list every carton that is more than half visible but has NO box, in "uncovered". For each give approx_box as \
[x1, y1, x2, y2], each a percentage 0-100 of the image width (x) or height (y), and a short note saying where it is.
Reply with JSON only, no commentary:
{"boxes": [{"id": 1, "distinct_carton": true, "visible_fraction": "more_than_half", "label_text": "none"}], \
"uncovered": [{"approx_box": [10, 20, 40, 60], "note": "top row, middle"}]}"""


def ask_spark(png: Path) -> dict:
    body = {
        "model": SPARK_MODEL,
        "input": [{"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": PROMPT},
            {"type": "input_image", "image_url": "data:image/png;base64," + base64.b64encode(png.read_bytes()).decode()},
        ]}],
    }
    resp = httpx.post(f"{BASE_URL}/responses", headers={"Authorization": f"Bearer {os.environ['MODEL_API_KEY']}"}, json=body, timeout=300)
    if resp.status_code != 200:
        sys.exit(f"spark -> {resp.status_code}: {resp.text[:500]}")
    text = "".join(b.get("text", "") for item in resp.json().get("output", []) for b in item.get("content", []) or [] if b.get("type") == "output_text")
    return json.loads(re.search(r"\{.*\}", text, re.S).group(0))


def is_verified(box: dict) -> bool:
    return bool(box.get("distinct_carton")) and box.get("visible_fraction") == "more_than_half"


def main() -> None:
    if len(sys.argv) < 2 or not os.environ.get("MODEL_API_KEY"):
        sys.exit(__doc__)
    clip, runs = sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 1
    stem = Path(clip).stem
    frames = parse_sam_output((OUT / f"sam_{stem}_cardboard_box.txt").read_text(encoding="utf-8"))
    n = best_frame(frames, LOOSE)
    boxes = filter_frame(frames[n], LOOSE)

    raw_png, shown_png = OUT / f"verify_{stem}_raw.png", OUT / f"verify_{stem}.png"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(TESTDATA / clip), "-vf", f"select=eq(n\\,{n})", "-vframes", "1", str(raw_png)], check=True)
    draw_boxes(raw_png, boxes, shown_png)

    results = []
    for k in range(runs):
        verdict = ask_spark(shown_png)
        by_id = {b["id"]: b for b in verdict.get("boxes", [])}
        verified = [is_verified(by_id.get(i, {})) for i in range(1, len(boxes) + 1)]
        uncovered = [tuple(u["approx_box"]) for u in verdict.get("uncovered", []) if len(u.get("approx_box", [])) == 4]
        results.append({"verified": verified, "uncovered": verdict.get("uncovered", []), "verdict": verdict})
        print(f"run {k + 1}: SAM {len(boxes)} -> verified {sum(verified)}, uncovered {len(uncovered)}, total {sum(verified) + len(uncovered)}")
        if k == runs - 1:
            draw_review(raw_png, boxes, verified, uncovered, OUT / f"verify_{stem}_review.png")

    agree = [sum(r["verified"][i] for r in results) for i in range(len(boxes))]
    print("per-box verified in N runs:", agree, f"(of {runs})")
    (OUT / f"verify_{stem}.json").write_text(json.dumps({"clip": stem, "frame": n, "sam_boxes": len(boxes), "runs": results}, indent=2), encoding="utf-8")
    raw_png.unlink()


if __name__ == "__main__":
    main()
