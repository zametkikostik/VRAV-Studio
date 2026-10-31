import asyncio
import json

from app.services.editing_plan import validate_plan
from app.services.plan_generate import _extract_json_object, generate_plan_llm

ASSETS = [
    {"id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "type": "video", "filename": "a.mp4"},
    {"id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", "type": "video", "filename": "b.mp4"},
]
PID = "11111111-1111-1111-1111-111111111111"


def test_extract_json_plain():
    assert _extract_json_object('{"version": "1.0", "x": 1}')["x"] == 1


def test_extract_json_fenced():
    assert _extract_json_object('Here:\n```json\n{"a": 2}\n```')["a"] == 2


def test_generate_mock_llm_path():
    plan, source = asyncio.new_event_loop().run_until_complete(
        generate_plan_llm(
            project_id=PID, assets=ASSETS, brief="edit the video clips with 2 second cuts",
            model="mock/default", chat_fn=None,
        )
    )
    assert source == "llm_mock"
    assert len(plan.clips) == 2
    validate_plan(plan.model_dump())


def test_generate_llm_fallback_on_bad_json():
    async def bad_chat(system, user, model):
        return "sorry I cannot help"

    plan, source = asyncio.new_event_loop().run_until_complete(
        generate_plan_llm(
            project_id=PID, assets=ASSETS, brief="edit videos",
            model="xai/grok", chat_fn=bad_chat,
        )
    )
    assert source == "llm_fallback_heuristics"
    assert len(plan.clips) >= 1


def test_generate_llm_valid_json():
    async def good_chat(system, user, model):
        return json.dumps({
            "version": "1.0",
            "project_id": PID,
            "source_asset_ids": [ASSETS[0]["id"]],
            "clips": [{
                "asset_id": ASSETS[0]["id"],
                "timeline_start_ms": 0,
                "duration_ms": 1000,
                "source_in_ms": 0,
            }],
        })

    plan, source = asyncio.new_event_loop().run_until_complete(
        generate_plan_llm(
            project_id=PID, assets=ASSETS, brief="one clip",
            model="xai/grok", chat_fn=good_chat,
        )
    )
    assert source == "llm"
    assert plan.clips[0].duration_ms == 1000
