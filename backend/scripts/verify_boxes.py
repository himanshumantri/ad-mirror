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
from PIL import Image

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
Then list every carton that is more than half visible but has NO box, in "uncovered". The image is __W__ pixels wide \
and __H__ pixels high. For each give approx_box as [x1, y1, x2, y2] in pixels of this image (x from 0 to __W__, y from \
0 to __H__), and a short note saying where it is.
Reply with JSON only, no commentary:
{"boxes": [{"id": 1, "distinct_carton": true, "visible_fraction": "more_than_half", "label_text": "none"}], \
"uncovered": [{"approx_box": [100, 120, 400, 360], "note": "top row, middle"}]}"""


def ask_spark(png: Path) -> dict:
    w, h = Image.open(png).size
    body = {
        "model": SPARK_MODEL,
        "input": [{"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": PROMPT.replace("__W__", str(w)).replace("__H__", str(h))},
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


def in_image(box: list, w: int, h: int) -> bool:
    """Reject boxes in the wrong units (percent, per-mille) instead of drawing them in the wrong place."""
    if len(box) != 4 or not all(isinstance(v, (int, float)) for v in box):
        return False
    x1, y1, x2, y2 = box
    return 0 <= x1 < x2 <= w * 1.02 and 0 <= y1 < y2 <= h * 1.02


def box_iou(a: tuple, b: tuple) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union else 0.0


def cluster_uncovered(per_run: list[list[tuple]], min_iou: float = 0.3) -> list[dict]:
    """Group uncovered boxes that overlap across runs; `runs` is how many runs saw that carton."""
    clusters: list[dict] = []
    for k, boxes in enumerate(per_run):
        for box in boxes:
            for c in clusters:
                if k not in c["seen"] and box_iou(box, c["boxes"][0]) >= min_iou:
                    c["boxes"].append(box)
                    c["seen"].add(k)
                    break
            else:
                clusters.append({"boxes": [box], "seen": {k}})
    for c in clusters:
        c["runs"] = len(c["seen"])
        c["box"] = tuple(sum(v) / len(c["boxes"]) for v in zip(*c["boxes"]))
    return clusters


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

    w, h = Image.open(raw_png).size
    results, per_run_uncovered = [], []
    for k in range(runs):
        verdict = ask_spark(shown_png)
        by_id = {b["id"]: b for b in verdict.get("boxes", [])}
        verified = [is_verified(by_id.get(i, {})) for i in range(1, len(boxes) + 1)]
        raw_unc = [u.get("approx_box", []) for u in verdict.get("uncovered", [])]
        uncovered = [tuple(b) for b in raw_unc if in_image(b, w, h)]
        rejected = len(raw_unc) - len(uncovered)
        per_run_uncovered.append(uncovered)
        results.append({"verified": verified, "uncovered": verdict.get("uncovered", []), "verdict": verdict})
        print(f"run {k + 1}: SAM {len(boxes)} -> verified {sum(verified)}, uncovered {len(uncovered)}" + (f" (+{rejected} dropped: box outside image)" if rejected else ""))

    need = runs // 2 + 1
    agree = [sum(r["verified"][i] for r in results) for i in range(len(boxes))]
    verified_majority = [a >= need for a in agree]
    clusters = cluster_uncovered(per_run_uncovered)
    flagged = [c for c in clusters if c["runs"] >= need]
    print(f"per-box verified in N runs: {agree} (of {runs})")
    print(f"majority: verified {sum(verified_majority)}; uncovered cartons seen in >= {need} runs: {len(flagged)}; seen in fewer: {len(clusters) - len(flagged)}")
    needs_review = bool(flagged) or any(0 < a < runs for a in agree) or not all(verified_majority)
    print("route:", "REVIEW" if needs_review else "auto-pass")
    draw_review(raw_png, boxes, verified_majority, [c["box"] for c in flagged], OUT / f"verify_{stem}_review.png")
    (OUT / f"verify_{stem}.json").write_text(json.dumps({"clip": stem, "frame": n, "sam_boxes": len(boxes), "runs": results}, indent=2), encoding="utf-8")
    raw_png.unlink()


if __name__ == "__main__":
    main()
