"""Muse Spark checks each SAM box on the clip's best frame, repeated N times and decided by majority.

Spark answers per box (distinct carton? more than half visible?) and lists cartons it sees with no box.
Uncovered cartons are review triggers, not counts: on the test clips they caught real misses but also
flagged a chair and small background cartons.
"""
import base64
import json
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from PIL import Image

from app.annotate import draw_boxes
from app.config import BASE_URL, OUT, SPARK_MODEL, auth_headers
from app.media import extract_frame
from app.segmentation import Detection, Filters, best_frame, filter_frame

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
    resp = httpx.post(f"{BASE_URL}/responses", headers=auth_headers(), json=body, timeout=300)
    resp.raise_for_status()
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


@dataclass
class Verification:
    frame: int
    boxes: list[Detection]
    runs: int
    votes: list[int]  # per SAM box: runs in which Spark verified it
    uncovered: list[tuple] = field(default_factory=list)  # pixel boxes seen in a majority of runs
    uncovered_minor: int = 0  # seen in fewer runs
    labels: list[str] = field(default_factory=list)

    @property
    def need(self) -> int:
        return self.runs // 2 + 1

    @property
    def majority(self) -> list[bool]:
        return [v >= self.need for v in self.votes]

    @property
    def count(self) -> int:
        return sum(self.majority)

    @property
    def disputed(self) -> int:
        return len(self.boxes) - self.count

    @property
    def split_votes(self) -> int:
        return sum(1 for v in self.votes if 0 < v < self.runs)


def _call_spark(video: Path, n: int, boxes: list[Detection], runs: int) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        raw, shown = Path(tmp) / "raw.png", Path(tmp) / "shown.png"
        extract_frame(video, n, raw)
        draw_boxes(raw, boxes, shown)
        results = []
        for _ in range(runs):
            verdict = ask_spark(shown)
            by_id = {b["id"]: b for b in verdict.get("boxes", [])}
            results.append({
                "verified": [is_verified(by_id.get(i, {})) for i in range(1, len(boxes) + 1)],
                "uncovered": verdict.get("uncovered", []),
                "verdict": verdict,
            })
    return {"clip": video.stem, "frame": n, "sam_boxes": len(boxes), "runs": results}


def verify_clip(video: Path, frames: dict[int, list[Detection]], runs: int = 3, refresh: bool = False) -> Verification:
    n = best_frame(frames, LOOSE)
    boxes = filter_frame(frames[n], LOOSE)
    if not boxes:
        return Verification(frame=n, boxes=[], runs=runs, votes=[])
    w, h = boxes[0].frame_w, boxes[0].frame_h

    cache = OUT / f"verify_{video.stem}.json"
    data = None
    if cache.exists() and not refresh:
        cached = json.loads(cache.read_text(encoding="utf-8"))
        if cached["frame"] == n and cached["sam_boxes"] == len(boxes) and len(cached["runs"]) >= runs:
            data = cached
    if data is None:
        data = _call_spark(video, n, boxes, runs)
        OUT.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(data, indent=2), encoding="utf-8")

    used = data["runs"][:runs]
    votes = [sum(r["verified"][i] for r in used) for i in range(len(boxes))]
    per_run = [[tuple(u["approx_box"]) for u in r["uncovered"] if in_image(u.get("approx_box", []), w, h)] for r in used]
    clusters = cluster_uncovered(per_run)
    need = runs // 2 + 1
    labels = sorted({b["label_text"] for b in used[-1]["verdict"].get("boxes", []) if b.get("label_text") not in (None, "none")})
    return Verification(
        frame=n, boxes=boxes, runs=runs, votes=votes,
        uncovered=[c["box"] for c in clusters if c["runs"] >= need],
        uncovered_minor=sum(1 for c in clusters if c["runs"] < need),
        labels=labels,
    )
