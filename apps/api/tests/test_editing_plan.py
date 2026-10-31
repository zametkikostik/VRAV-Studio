import pytest
from pydantic import ValidationError
from app.services.editing_plan import plan_to_render_clips, validate_plan


def test_valid_plan():
    plan = validate_plan({
        "version": "1.0",
        "project_id": "11111111-1111-1111-1111-111111111111",
        "source_asset_ids": ["aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"],
        "clips": [{
            "asset_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "timeline_start_ms": 0, "duration_ms": 1000, "source_in_ms": 0,
        }],
        "output": {"width": 640, "height": 360, "fps": 25},
    })
    assert plan.clips[0].duration_ms == 1000
    assert len(plan_to_render_clips(plan)) == 1


def test_rejects_empty_clips():
    with pytest.raises(ValidationError):
        validate_plan({"project_id": "11111111-1111-1111-1111-111111111111", "clips": []})


def test_rejects_bad_source_window():
    with pytest.raises(ValidationError):
        validate_plan({
            "project_id": "11111111-1111-1111-1111-111111111111",
            "source_asset_ids": ["aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"],
            "clips": [{
                "asset_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "source_in_ms": 500, "source_out_ms": 100,
                "duration_ms": 50, "timeline_start_ms": 0,
            }],
        })


def test_asset_must_be_in_sources_when_listed():
    with pytest.raises(ValidationError):
        validate_plan({
            "project_id": "11111111-1111-1111-1111-111111111111",
            "source_asset_ids": ["bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"],
            "clips": [{
                "asset_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "duration_ms": 100, "timeline_start_ms": 0,
            }],
        })
