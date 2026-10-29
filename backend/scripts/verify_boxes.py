"""Ask Muse Spark to check each SAM box on a clip's best frame. Needs MODEL_API_KEY.

    python scripts/verify_boxes.py "Clip B.mp4"

Reads cached testdata/out/sam_<clip>_cardboard_box.txt (run smoke_checks.py sam first); writes
testdata/out/verify_<clip>.json and testdata/out/verify_<clip>.png (the frame Spark saw).
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
from app.annotate import draw_boxes  # noqa: E402
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
Also give uncovered_cartons: how many cartons that are more than half visible have NO box.
Reply with JSON only, no commentary:
{"boxes": [{"id": 1, "distinct_carton": true, "visible_fraction": "more_than_half", "label_text": "none"}], "uncovered_cartons": 0}"""


def main() -> None:
    if len(sys.argv) < 2 or not os.environ.get("MODEL_API_KEY"):
        sys.exit(__doc__)
    clip = sys.argv[1]
    stem = Path(clip).stem
    frames = parse_sam_output((OUT / f"sam_{stem}_cardboard_box.txt").read_text(encoding="utf-8"))
    n = best_frame(frames, LOOSE)
    boxes = filter_frame(frames[n], LOOSE)

    raw_png, shown_png = OUT / f"verify_{stem}_raw.png", OUT / f"verify_{stem}.png"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(TESTDATA / clip), "-vf", f"select=eq(n\\,{n})", "-vframes", "1", str(raw_png)], check=True)
    draw_boxes(raw_png, boxes, shown_png)
    raw_png.unlink()

    body = {
        "model": SPARK_MODEL,
        "input": [{"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": PROMPT},
            {"type": "input_image", "image_url": "data:image/png;base64," + base64.b64encode(shown_png.read_bytes()).decode()},
        ]}],
    }
    resp = httpx.post(f"{BASE_URL}/responses", headers={"Authorization": f"Bearer {os.environ['MODEL_API_KEY']}"}, json=body, timeout=300)
    print("spark ->", resp.status_code)
    if resp.status_code != 200:
        sys.exit(resp.text[:500])
    text = "".join(b.get("text", "") for item in resp.json().get("output", []) for b in item.get("content", []) or [] if b.get("type") == "output_text")
    verdict = json.loads(re.search(r"\{.*\}", text, re.S).group(0))

    verified = [b for b in verdict["boxes"] if b["distinct_carton"] and b["visible_fraction"] == "more_than_half"]
    result = {
        "clip": stem, "frame": n, "sam_boxes": len(boxes), "spark_verified": len(verified),
        "uncovered_cartons": verdict.get("uncovered_cartons", 0), "verdict": verdict,
    }
    (OUT / f"verify_{stem}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"frame {n}: SAM {len(boxes)} boxes -> Spark verified {len(verified)}, uncovered {result['uncovered_cartons']}")
    for b in verdict["boxes"]:
        print(f"  box {b['id']}: distinct={b['distinct_carton']} visible={b['visible_fraction']} label={b['label_text']!r}")


if __name__ == "__main__":
    main()
