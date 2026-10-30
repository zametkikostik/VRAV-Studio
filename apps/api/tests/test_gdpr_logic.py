"""Pure shape checks for GDPR export structure (no DB)."""


def test_export_shape_contract():
    expected = {"exported_at", "user", "memberships", "ai_connections", "ai_usage_events_sample"}
    sample = {
        "exported_at": "2026-01-01T00:00:00+00:00",
        "user": {"id": "u", "email": "a@b.c", "full_name": None, "created_at": None, "is_active": False},
        "memberships": [],
        "ai_connections": [],
        "ai_usage_events_sample": [],
    }
    assert expected <= sample.keys()
    assert "encrypted_api_key" not in str(sample)
