"""Iteration 11: real AI editing plan generation (deterministic adapter boundary)."""
from __future__ import annotations

import asyncio
import json
import uuid

import pytest

from app.services.editing_plan import PlanValidationError
from app.services.plan_generate import (
    generate_plan_llm,
    _extract_json_object,
    asset_row_to_context,
    duration_ms_from_asset_row,
    build_limitations,
)


def _assets(n=2):
    out = []
    for i in range(n):
        out.append(
            {
                "id": str(uuid.uuid4()),
                "type": "video",
                "filename": f"clip{i}.mp4",
                "duration_ms": 10_000,
                "transcript": f"hello world {i}" if i == 0 else None,
            }
        )
    return out


def test_extract_json_object_plain():
    data = _extract_json_object('{"version": "1.0", "x": 1}')
    assert data["x"] == 1


def test_extract_json_object_fenced():
    data = _extract_json_object('```json\n{"version": "1.0", "ok": true}\n```')
    assert data["ok"] is True


def test_extract_json_malformed():
    with pytest.raises(PlanValidationError):
        _extract_json_object("not json at all")


def test_mock_path_no_chat_fn():
    assets = _assets()
    plan, source = asyncio.run(
        generate_plan_llm(
            project_id=str(uuid.uuid4()),
            assets=assets,
            brief="cut the intro",
            model="mock/default",
            chat_fn=None,
        )
    )
    assert source == "llm_mock"
    assert plan.clips


def test_provider_unavailable_without_chat_fn():
    assets = _assets()
    with pytest.raises(PlanValidationError) as ei:
        asyncio.run(
            generate_plan_llm(
                project_id=str(uuid.uuid4()),
                assets=assets,
                brief="x",
                model="openrouter/auto",
                chat_fn=None,
            )
        )
    assert "provider_unavailable" in ei.value.errors[0]


def test_llm_valid_response():
    assets = _assets()
    pid = str(uuid.uuid4())
    aid = assets[0]["id"]

    async def chat_fn(system, user, model):
        return json.dumps(
            {
                "version": "1.0",
                "project_id": pid,
                "source_asset_ids": [aid],
                "clips": [
                    {
                        "asset_id": aid,
                        "track_type": "video",
                        "timeline_start_ms": 0,
                        "duration_ms": 2000,
                        "source_in_ms": 0,
                        "source_out_ms": 2000,
                    }
                ],
                "subtitles": [],
                "output": {"width": 1280, "height": 720, "fps": 30},
                "notes": "ok",
            }
        )

    plan, source = asyncio.run(
        generate_plan_llm(
            project_id=pid, assets=assets, brief="short", model="xai/grok", chat_fn=chat_fn
        )
    )
    assert source == "llm"
    assert plan.clips[0].asset_id == aid


def test_llm_rejects_unknown_asset_id():
    assets = _assets()
    pid = str(uuid.uuid4())
    fake = str(uuid.uuid4())

    async def chat_fn(system, user, model):
        return json.dumps(
            {
                "version": "1.0",
                "project_id": pid,
                "source_asset_ids": [fake],
                "clips": [
                    {
                        "asset_id": fake,
                        "track_type": "video",
                        "timeline_start_ms": 0,
                        "duration_ms": 1000,
                        "source_in_ms": 0,
                    }
                ],
            }
        )

    with pytest.raises(PlanValidationError):
        asyncio.run(
            generate_plan_llm(
                project_id=pid, assets=assets, brief="x", model="xai/g", chat_fn=chat_fn
            )
        )


def test_llm_rejects_source_out_beyond_duration():
    assets = _assets(1)
    pid = str(uuid.uuid4())
    aid = assets[0]["id"]

    async def chat_fn(system, user, model):
        return json.dumps(
            {
                "version": "1.0",
                "project_id": pid,
                "source_asset_ids": [aid],
                "clips": [
                    {
                        "asset_id": aid,
                        "track_type": "video",
                        "timeline_start_ms": 0,
                        "duration_ms": 5000,
                        "source_in_ms": 0,
                        "source_out_ms": 99_000,
                    }
                ],
            }
        )

    with pytest.raises(PlanValidationError):
        asyncio.run(
            generate_plan_llm(
                project_id=pid, assets=assets, brief="x", model="xai/g", chat_fn=chat_fn
            )
        )


def test_llm_malformed_json_no_heuristic_fallback():
    assets = _assets()
    pid = str(uuid.uuid4())

    async def chat_fn(system, user, model):
        return "I cannot help with that"

    with pytest.raises(PlanValidationError):
        asyncio.run(
            generate_plan_llm(
                project_id=pid, assets=assets, brief="x", model="xai/g", chat_fn=chat_fn
            )
        )


def test_provider_error_propagates():
    assets = _assets()

    async def chat_fn(system, user, model):
        raise TimeoutError("upstream timeout")

    with pytest.raises(PlanValidationError) as ei:
        asyncio.run(
            generate_plan_llm(
                project_id=str(uuid.uuid4()),
                assets=assets,
                brief="x",
                model="xai/g",
                chat_fn=chat_fn,
            )
        )
    assert "provider_error" in ei.value.errors[0]


def test_empty_assets():
    with pytest.raises(PlanValidationError):
        asyncio.run(
            generate_plan_llm(
                project_id=str(uuid.uuid4()), assets=[], brief="x", model="mock/default"
            )
        )


def test_duration_from_metadata():
    class A:
        metadata_ = {"duration_ms": 5500}
        id = uuid.uuid4()
        type = "video"
        filename = "a.mp4"
        transcript = None
        mime_type = "video/mp4"

    assert duration_ms_from_asset_row(A()) == 5500
    ctx = asset_row_to_context(A())
    assert ctx["duration_ms"] == 5500


def test_limitations_list():
    lim = build_limitations(_assets())
    assert "no_visual_frame_analysis" in lim
    assert any("transcript" in x for x in lim)
