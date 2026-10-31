from app.services.editing_plan import PlanValidationError, plan_from_brief, validate_plan

ASSETS = [
    {"id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "type": "video"},
    {"id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", "type": "video"},
    {"id": "cccccccc-cccc-cccc-cccc-cccccccccccc", "type": "audio"},
]


def test_brief_sequential_skips_audio():
    plan = plan_from_brief("11111111-1111-1111-1111-111111111111", ASSETS, "Edit the video clips together")
    assert len(plan.clips) == 2
    assert all(c.asset_id != "cccccccc-cccc-cccc-cccc-cccccccccccc" for c in plan.clips)
    validate_plan(plan.model_dump())
    assert "heuristics" in (plan.notes or "").lower()


def test_brief_duration_seconds():
    plan = plan_from_brief("11111111-1111-1111-1111-111111111111", ASSETS, "quick 1.5 second cuts")
    assert plan.clips[0].duration_ms == 1500


def test_brief_first_n():
    plan = plan_from_brief("11111111-1111-1111-1111-111111111111", ASSETS, "use only the first 1 clip")
    assert len(plan.clips) == 1


def test_brief_subtitle():
    plan = plan_from_brief("11111111-1111-1111-1111-111111111111", ASSETS, "Add a title subtitle on the opening")
    assert len(plan.subtitles) >= 1


def test_brief_empty_raises():
    try:
        plan_from_brief("11111111-1111-1111-1111-111111111111", ASSETS, "   ")
        assert False
    except PlanValidationError:
        pass
