"""Iteration 4 Task 1: architecture doc present and aligned with compiler."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_ffmpeg_compiler_doc_exists():
    p = ROOT / "docs/architecture/FFMPEG_COMPILER.md"
    assert p.exists()
    text = p.read_text()
    assert "argv" in text.lower()
    assert "TimelineDefinition" in text
    assert "shell" in text.lower()


def test_doc_mentions_track_lanes():
    text = (ROOT / "docs/architecture/FFMPEG_COMPILER.md").read_text()
    assert "video" in text
    assert "audio" in text
    assert "overlay" in text
