"""Score cached SAM output in testdata/out/ against testdata/clip_truth.csv. Offline: no API key needed.

    python scripts/evaluate.py [phrase]

clip_truth.csv columns: clip, true_boxes   (number of target cartons actually in frame; blank = unknown)
Raw model output is cached by smoke_checks.py as testdata/out/sam_<clip>_<phrase>.txt
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.segmentation import count_clip, parse_sam_output  # noqa: E402

TESTDATA = Path(__file__).resolve().parents[2] / "testdata"


def truth() -> dict[str, str]:
    path = TESTDATA / "clip_truth.csv"
    if not path.exists():
        return {}
    with path.open(newline="") as fh:
        return {row["clip"]: row["true_boxes"] for row in csv.DictReader(fh)}


def main() -> None:
    phrase = (sys.argv[1] if len(sys.argv) > 1 else "cardboard box").replace(" ", "_")
    known = truth()
    print(f"{'clip':8} {'frames':>6} {'raw ids':>7} {'raw/frame':>9} {'filt med':>8} {'filt p80':>8} {'filt max':>8} {'truth':>6}")
    for path in sorted((TESTDATA / "out").glob(f"sam_Clip ?_{phrase}.txt")):
        clip = path.stem.split("_")[1]
        c = count_clip(parse_sam_output(path.read_text(encoding="utf-8")))
        true = known.get(clip) or "?"
        print(f"{clip:8} {c.frames:6} {c.raw_unique_ids:7} {c.raw_median_per_frame:9.1f} {c.filtered_median:8.1f} {c.filtered_p80:8} {c.filtered_max:8} {true:>6}")


if __name__ == "__main__":
    main()
