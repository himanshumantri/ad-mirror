"""Draw numbered detection boxes on a frame (plain image drawing, no model)."""
from pathlib import Path

from PIL import Image, ImageDraw

from app.segmentation import Detection

COLOR = "#e6194b"
VERIFIED, DISPUTED, UNCOVERED = "#2e9e4f", "#f58231", "#1f6feb"


def draw_boxes(image_path: Path, detections: list[Detection], out_path: Path) -> None:
    """Box i (1-based, in list order) is labelled `i` at its top-left corner."""
    img = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    for i, d in enumerate(detections, start=1):
        draw.rectangle([d.x1, d.y1, d.x2, d.y2], outline=COLOR, width=4)
        draw.rectangle([d.x1, d.y1, d.x1 + 30, d.y1 + 20], fill=COLOR)
        draw.text((d.x1 + 6, d.y1 + 4), str(i), fill="white")
    img.save(out_path)


def draw_review(
    image_path: Path,
    detections: list[Detection],
    verified: list[bool],
    uncovered: list[tuple[float, float, float, float]],
    out_path: Path,
) -> None:
    """Review frame: green = SAM box Spark agrees with, orange = SAM box Spark disputes,
    blue '?' = carton Spark says has no box (approx box as 0-100 percentages of image width/height)."""
    img = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    for i, (d, ok) in enumerate(zip(detections, verified), start=1):
        color = VERIFIED if ok else DISPUTED
        draw.rectangle([d.x1, d.y1, d.x2, d.y2], outline=color, width=4)
        draw.rectangle([d.x1, d.y1, d.x1 + 30, d.y1 + 20], fill=color)
        draw.text((d.x1 + 6, d.y1 + 4), str(i), fill="white")
    w, h = img.size
    for x1, y1, x2, y2 in uncovered:
        box = [x1 / 100 * w, y1 / 100 * h, x2 / 100 * w, y2 / 100 * h]
        draw.rectangle(box, outline=UNCOVERED, width=4)
        draw.rectangle([box[0], box[1], box[0] + 30, box[1] + 20], fill=UNCOVERED)
        draw.text((box[0] + 10, box[1] + 4), "?", fill="white")
    img.save(out_path)
