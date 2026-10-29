"""Parse SAM 3.1 video output and turn it into a filtered instance count.

Output format (https://dev.meta.ai/docs/sam/segmenting): one line per frame, `<Nf>` frame marker, then
comma-separated records `<id><|box;x1;y1;x2;y2;w;h;c=conf|><|mask;...|>`. Raw unique ids over a whole clip
are not a count: ids are only stable within a response, the docs warn against relying on them across exit,
re-entry or occlusion, and the output carries fragments and whole-frame boxes. So counting is done per frame
on filtered boxes, then summarised over the clip.
"""
import re
import statistics
from dataclasses import dataclass

_FRAME = re.compile(r"<(\d+)f>")
_BOX = re.compile(r"(?:>|,)(\d+)<\|box;x1=(\d+);y1=(\d+);x2=(\d+);y2=(\d+);w=(\d+);h=(\d+);c=([\d.]+)\|>")


@dataclass(frozen=True)
class Detection:
    frame: int
    obj_id: int
    x1: int
    y1: int
    x2: int
    y2: int
    frame_w: int
    frame_h: int
    conf: float

    @property
    def area_frac(self) -> float:
        return (self.x2 - self.x1 + 1) * (self.y2 - self.y1 + 1) / (self.frame_w * self.frame_h)


def parse_sam_output(text: str) -> dict[int, list[Detection]]:
    """Frame number -> detections on that frame. Mask payloads are ignored."""
    frames: dict[int, list[Detection]] = {}
    for line in text.splitlines():
        m = _FRAME.match(line)
        if not m:
            continue
        frame = int(m.group(1))
        frames[frame] = [
            Detection(frame, int(o), int(x1), int(y1), int(x2), int(y2), int(w), int(h), float(c))
            for o, x1, y1, x2, y2, w, h, c in _BOX.findall(line)
        ]
    return frames


def iou(a: Detection, b: Detection) -> float:
    ix = max(0, min(a.x2, b.x2) - max(a.x1, b.x1) + 1)
    iy = max(0, min(a.y2, b.y2) - max(a.y1, b.y1) + 1)
    inter = ix * iy
    area = lambda d: (d.x2 - d.x1 + 1) * (d.y2 - d.y1 + 1)
    return inter / (area(a) + area(b) - inter)


@dataclass(frozen=True)
class Filters:
    min_conf: float = 0.8
    min_area_frac: float = 0.04
    max_area_frac: float = 0.7  # drops whole-frame boxes
    nms_iou: float = 0.5


def filter_frame(dets: list[Detection], f: Filters = Filters()) -> list[Detection]:
    kept = [d for d in dets if d.conf >= f.min_conf and f.min_area_frac <= d.area_frac <= f.max_area_frac]
    kept.sort(key=lambda d: d.conf, reverse=True)
    out: list[Detection] = []
    for d in kept:
        if all(iou(d, o) < f.nms_iou for o in out):
            out.append(d)
    return out


@dataclass
class ClipCount:
    frames: int
    raw_unique_ids: int
    raw_median_per_frame: float
    filtered_median: float
    filtered_p80: int
    filtered_max: int


def count_clip(frames: dict[int, list[Detection]], f: Filters = Filters()) -> ClipCount:
    ids = {d.obj_id for dets in frames.values() for d in dets}
    raw = [len(dets) for dets in frames.values()]
    filtered = sorted(len(filter_frame(dets, f)) for dets in frames.values())
    return ClipCount(
        frames=len(frames),
        raw_unique_ids=len(ids),
        raw_median_per_frame=statistics.median(raw),
        filtered_median=statistics.median(filtered),
        filtered_p80=filtered[int(0.8 * (len(filtered) - 1))],
        filtered_max=filtered[-1],
    )
