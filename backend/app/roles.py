"""Separation of duties: whoever filmed a shelf cannot also decide its count."""
from fastapi import HTTPException

from app.tables import Clip


def require_not_capturer(clip: Clip, reviewer: str) -> None:
    if clip.captured_by and clip.captured_by.strip().casefold() == reviewer.strip().casefold():
        raise HTTPException(409, f"{reviewer.strip()} captured this clip, so someone else must review it")
