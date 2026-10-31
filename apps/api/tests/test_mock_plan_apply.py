import pytest
from app.services.editing_plan import PlanValidationError, generate_mock_plan, plan_to_render_clips, validate_plan


def test_generate_mock_sequential():
    assets = [
        {"id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "type": "video"},
        {"id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", "type": "video"},
    ]
    plan = generate_mock_plan("11111111-1111-1111-1111-111111111111", assets, default_clip_ms=2000)
    assert len(plan.clips) == 2
    assert plan.clips[0].timeline_start_ms == 0
    assert plan.clips[1].timeline_start_ms == 2000
    assert plan.notes and "mock" in plan.notes.lower()
    validate_plan(plan.model_dump())
    assert len(plan_to_render_clips(plan)) == 2


def test_generate_mock_skips_audio_only_project():
    with pytest.raises(PlanValidationError):
        generate_mock_plan("11111111-1111-1111-1111-111111111111",
                           [{"id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "type": "audio"}])


def test_generate_mock_empty():
    with pytest.raises(PlanValidationError):
        generate_mock_plan("11111111-1111-1111-1111-111111111111", [])
