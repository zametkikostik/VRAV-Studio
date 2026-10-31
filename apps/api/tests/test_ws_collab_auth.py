from __future__ import annotations

from pathlib import Path


def test_ws_collab_requires_auth_before_accept():
    src = Path(__file__).resolve().parents[1] / "app" / "api" / "ws_collab.py"
    text = src.read_text()
    assert "_authorize_room" in text
    assert "decode_access_token" in text
    assert "4401" in text
    assert text.find("await _authorize_room") < text.find("await websocket.accept()")


def test_ws_collab_membership_query_present():
    text = (Path(__file__).resolve().parents[1] / "app" / "api" / "ws_collab.py").read_text()
    assert "OrganizationMember" in text
    assert "project.organization_id" in text
