"""One clip through the models: narration -> location and item, SAM count, Spark verification, evidence frame.

The count is the number of SAM boxes Spark verifies in a majority of runs. Anything else (disputed boxes,
split votes, cartons Spark sees with no box, an unresolved location) marks the clip for human review.
"""
from pathlib import Path

from app import narration
from app.annotate import draw_review
from app.config import OUT
from app.media import extract_frame
from app.reconcile import BookLine, ClipResult
from app.sam_client import segment_video
from app.segmentation import parse_sam_output
from app.verification import verify_clip
from app.voice_client import transcribe

SAM_PHRASE = "cardboard box"  # generic carton prompt; later derived from the plan's item packaging


def run_clip(video: Path, book: list[BookLine], runs: int = 3, refresh_verification: bool = False) -> ClipResult:
    items = sorted({b.item for b in book})
    locations = sorted({b.location for b in book})

    transcript = transcribe(video, keywords=items).get("transcript", "")
    location = narration.resolve_location(transcript, locations)
    item = narration.resolve_item(transcript, items)

    frames = parse_sam_output(segment_video(video, SAM_PHRASE))
    ver = verify_clip(video, frames, runs=runs, refresh=refresh_verification)

    reasons: list[str] = []
    if location is None:
        reasons.append("location not recognised from narration")
    if ver.disputed:
        reasons.append(f"{ver.disputed} box(es) Spark disputes")
    if ver.split_votes:
        reasons.append(f"{ver.split_votes} box(es) with split Spark votes")
    if ver.uncovered:
        reasons.append(f"{len(ver.uncovered)} carton(s) Spark sees with no box")

    evidence = ""
    if ver.boxes:
        evidence_dir = OUT / "evidence"
        raw, evidence_path = evidence_dir / f"{video.stem}_raw.png", evidence_dir / f"{video.stem}_review.png"
        extract_frame(video, ver.frame, raw)
        draw_review(raw, ver.boxes, ver.majority, ver.uncovered, evidence_path)
        raw.unlink()
        evidence = evidence_path.relative_to(OUT).as_posix()  # relative, so the report travels with the evidence pack

    return ClipResult(
        clip=video.name, location=location, item=item, counted=ver.count,
        needs_review=bool(reasons), reasons=reasons, evidence=evidence, transcript=transcript,
    )
