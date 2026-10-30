from pathlib import Path

from app.services.media import ffmpeg_available, probe


def test_ffmpeg_available_is_bool():
    assert isinstance(ffmpeg_available(), bool)


def test_probe_missing_file():
    try:
        probe("/tmp/vrav-definitely-missing-file-xyz.mp4")
        raise AssertionError("should raise")
    except FileNotFoundError:
        pass


def test_probe_existing_file_without_ffprobe(tmp_path: Path):
    f = tmp_path / "a.bin"
    f.write_bytes(b"not-a-video")
    try:
        result = probe(f)
        assert "status" in result or "format" in result or "streams" in result
    except RuntimeError:
        pass
