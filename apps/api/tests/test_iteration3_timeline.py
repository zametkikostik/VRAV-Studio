"""Iteration 3: TimelineDefinition, Asset AI fields, FFmpegCompilerWorker."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.services.ffmpeg_compiler import CompileError, FFmpegCompilerWorker, compile_timeline
from app.services.timeline_definition import (
    TimelineDefinition,
    timeline_json_schema,
    validate_timeline,
)


SAMPLE = {
    "version": "1.0",
    "project_id": "11111111-1111-1111-1111-111111111111",
    "source_asset_ids": ["aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"],
    "clips": [
        {
            "asset_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "source_in_ms": 0,
            "duration_ms": 2000,
            "timeline_start_ms": 0,
            "track_type": "video",
        }
    ],
    "output": {"width": 640, "height": 360, "fps": 24},
}


def test_validate_timeline_ok():
    tl = validate_timeline(SAMPLE)
    assert isinstance(tl, TimelineDefinition)
    assert tl.clips[0].duration_ms == 2000


def test_validate_timeline_rejects_empty_clips():
    bad = {**SAMPLE, "clips": []}
    with pytest.raises(Exception):
        validate_timeline(bad)


def test_timeline_json_schema_has_clips():
    schema = timeline_json_schema()
    assert "properties" in schema
    assert "clips" in schema["properties"]


def test_compiler_builds_argv_without_shell():
    paths = {"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa": "/tmp/fake_src.mp4"}
    compiled = compile_timeline(SAMPLE, paths, "/tmp/vrav_work", "/tmp/vrav_out/out.mp4")
    assert len(compiled.segments) == 1
    argv = compiled.segments[0].argv
    assert argv[0] == "ffmpeg"
    assert "-i" in argv
    assert all(isinstance(x, str) for x in argv)
    assert not any(";" in x or "|" in x or "&&" in x for x in argv)


def test_compiler_missing_asset_raises():
    with pytest.raises(CompileError, match="missing asset"):
        compile_timeline(SAMPLE, {}, "/tmp/w", "/tmp/o.mp4")


def test_asset_model_has_transcript_embedding():
    text = (Path(__file__).resolve().parents[1] / "app/models/project.py").read_text()
    assert "transcript" in text
    assert "embedding" in text


def test_migration_012_exists():
    mig = Path(__file__).resolve().parents[3] / "infra/alembic/versions/012_asset_transcript_embedding.py"
    assert mig.exists()
    body = mig.read_text()
    assert "transcript" in body
    assert "embedding" in body
    assert 'down_revision = "011"' in body


def test_ffmpeg_compiler_worker_class():
    w = FFmpegCompilerWorker(ffmpeg_bin="ffmpeg")
    paths = {"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa": "/data/a.mp4"}
    c = w.compile(SAMPLE, paths, "/tmp/w", "/tmp/out.mp4")
    assert c.width == 640
    assert c.fps == 24.0
