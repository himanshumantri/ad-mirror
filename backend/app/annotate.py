"""Draw numbered detection boxes on a frame (plain image drawing, no model)."""
from pathlib import Path

from PIL import Image, ImageDraw

from app.segmentation import Detection

COLOR = "#e6194b"


def draw_boxes(image_path: Path, detections: list[Detection], out_path: Path) -> None:
    """Box i (1-based, in list order) is labelled `i` at its top-left corner."""
    img = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    for i, d in enumerate(detections, start=1):
        draw.rectangle([d.x1, d.y1, d.x2, d.y2], outline=COLOR, width=4)
        draw.rectangle([d.x1, d.y1, d.x1 + 30, d.y1 + 20], fill=COLOR)
        draw.text((d.x1 + 6, d.y1 + 4), str(i), fill="white")
    img.save(out_path)
