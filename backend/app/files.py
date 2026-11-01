"""Keep the small image files a clip produces (evidence frame, unmarked frame) in the database as well as on disk.

The disk on a free host is wiped on restart; the database is not. A file is saved under its path relative to the data
folder, and written back to that path on demand, so code that wants a file on disk does not need to know the difference.
Videos are not kept here: they are only needed while a clip is being counted.
"""
from pathlib import Path

from sqlalchemy.orm import Session

from app.tables import Blob


def save_blob(s: Session, out: Path, relative: str) -> bool:
    """Store the file at out/relative under that key. Returns False when there is no such file."""
    path = out / relative
    if not path.is_file():
        return False
    blob = s.get(Blob, relative) or Blob(key=relative)
    blob.data = path.read_bytes()
    s.add(blob)
    return True


def restore_blob(s: Session, out: Path, relative: str) -> Path | None:
    """The file at out/relative, written back from the database if the disk has lost it; None if neither has it."""
    path = out / relative
    if path.is_file():
        return path
    blob = s.get(Blob, relative)
    if blob is None:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(blob.data)
    return path
