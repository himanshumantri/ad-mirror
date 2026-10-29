"""Ask Muse Spark to check each SAM box on a clip's best frame, N times. Needs MODEL_API_KEY.

    python scripts/verify_boxes.py "Clip B.mp4" [runs]

Reads cached testdata/out/sam_<clip>_cardboard_box.txt (run smoke_checks.py sam first) and always asks Spark
again. Writes testdata/out/verify_<clip>.json and evidence/<clip>_review.png (green = SAM box Spark agrees with,
orange = disputed, blue ? = carton Spark says has no box).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.annotate import draw_review  # noqa: E402
from app.config import OUT, TESTDATA  # noqa: E402
from app.media import extract_frame  # noqa: E402
from app.sam_client import segment_video  # noqa: E402
from app.segmentation import parse_sam_output  # noqa: E402
from app.verification import verify_clip  # noqa: E402


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    video = TESTDATA / sys.argv[1]
    runs = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    ver = verify_clip(video, parse_sam_output(segment_video(video, "cardboard box")), runs=runs, refresh=True)

    print(f"frame {ver.frame}: SAM {len(ver.boxes)} boxes; per-box verified in N runs: {ver.votes} (of {runs})")
    print(f"majority: verified {ver.count}; uncovered cartons seen in >= {ver.need} runs: {len(ver.uncovered)}; seen in fewer: {ver.uncovered_minor}")
    print("route:", "REVIEW" if ver.disputed or ver.split_votes or ver.uncovered else "auto-pass")

    raw, review = OUT / "evidence" / f"{video.stem}_raw.png", OUT / "evidence" / f"{video.stem}_review.png"
    extract_frame(video, ver.frame, raw)
    draw_review(raw, ver.boxes, ver.majority, ver.uncovered, review)
    raw.unlink()
    print("review frame:", review)


if __name__ == "__main__":
    main()
