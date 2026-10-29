"""Interfaces for the Meta models. Real and mock adapters implement these so the
pipeline never depends on a specific deployment (hosted API now, Glimmer/on-prem later)."""
from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class Box:
    x: float
    y: float
    w: float
    h: float


@dataclass
class TrackedInstance:
    track_id: str
    first_frame: int
    last_frame: int
    score: float


@dataclass
class CountResult:
    instances: list[TrackedInstance] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.instances)


class Segmenter(Protocol):
    """Segment Anything Model 3.1: count and track instances in a clip."""

    def count(self, video_path: str, phrase: str | None = None, exemplar: Box | None = None) -> CountResult: ...


@dataclass
class LabelRead:
    frame: int
    text: str
    kind: str  # "label" | "model_number" | "serial" | "pack_size"
    confidence: float


class Reader(Protocol):
    """Muse Spark: read labels and serials, classify items, check the capture."""

    def read_labels(self, frame_paths: list[str]) -> list[LabelRead]: ...


@dataclass
class Segment:
    start_s: float
    end_s: float
    text: str


class Transcriber(Protocol):
    """Muse Voice Transcribe: narration to timestamped text."""

    def transcribe(self, audio_path: str, keywords: list[str] | None = None) -> list[Segment]: ...
