"""ffmpeg helpers. ffmpeg is a video tool, not a model."""
import subprocess
import tempfile
from pathlib import Path


def extract_frame(video: Path, n: int, out: Path) -> None:
    """Write frame number `n` (0-based, display orientation) as an image."""
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-vf", f"select=eq(n\\,{n})", "-vframes", "1", str(out)], check=True)


def wav_bytes(video: Path) -> bytes:
    """Mono 16-bit 16 kHz WAV of the clip's audio, as the transcribe endpoint requires."""
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "audio.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)], check=True)
        return wav.read_bytes()
