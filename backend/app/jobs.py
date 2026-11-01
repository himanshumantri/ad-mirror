"""Run one uploaded clip through the pipeline and store the result. Runs in the background after the upload returns."""
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.config import OUT
from app.files import save_blob
from app.reconcile import BookLine, ClipResult
from app.tables import BookLineRow, Clip

Runner = Callable[[Path, list[BookLine]], ClipResult]


def book_lines(session: Session) -> list[BookLine]:
    return [BookLine(r.item, r.location, r.book_qty, r.unit_cost) for r in session.scalars(select(BookLineRow).order_by(BookLineRow.id))]


def process_clip(sessions: sessionmaker[Session], clip_id: str, uploads: Path, runner: Runner, out: Path = OUT) -> None:
    with sessions() as s:
        clip = s.get(Clip, clip_id)
        clip.status = "running"
        s.commit()
        try:
            result = runner(uploads / clip.filename, book_lines(s))
        except Exception as e:  # a model or network failure must end as a visible failed job, not a stuck one
            clip.status, clip.error = "failed", f"{type(e).__name__}: {e}"[:2000]
        else:
            clip.status = "done"
            clip.location, clip.item, clip.counted = result.location, result.item, result.counted
            clip.needs_review, clip.reasons = result.needs_review, result.reasons
            clip.evidence, clip.transcript = result.evidence, result.transcript[:4000]
            stem = Path(clip.filename).stem
            for relative in (result.evidence, f"evidence/{stem}_raw.png"):
                if relative:
                    save_blob(s, out, relative)
        clip.finished_at = datetime.now(UTC)
        s.commit()
