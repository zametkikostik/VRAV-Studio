"""P1-F token revoke/rotation and P1-G WS ticket regression tests."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]


def test_p1f_revoked_jti_model_and_migration():
    assert (ROOT / "app/models/auth_token.py").exists()
    mig = REPO / "infra/alembic/versions/011_revoked_jtis_token_version.py"
    assert mig.exists()
    body = mig.read_text()
    assert "revoked_jtis" in body
    assert "token_version" in body


def test_p1f_user_has_token_version():
    text = (ROOT / "app/models/user.py").read_text()
    assert "token_version" in text


def test_p1f_jwt_includes_ver_claim():
    text = (ROOT / "app/core/security.py").read_text()
    assert "token_version" in text
    assert "ver" in text


def test_p1f_deps_checks_jti_and_version():
    text = (ROOT / "app/api/deps.py").read_text()
    assert "is_jti_revoked" in text
    assert "token_version" in text


def test_p1f_refresh_rotates_and_logout_exists():
    text = (ROOT / "app/api/auth.py").read_text()
    assert "/logout" in text
    assert "revoke_jti" in text
    assert "token_version" in text


def test_p1f_password_reset_bumps_token_version():
    text = (ROOT / "app/api/auth.py").read_text()
    assert "token_version" in text
    assert "password_updated" in text


def test_p1g_collab_ticket_endpoint():
    text = (ROOT / "app/api/ws_collab.py").read_text()
    assert "/collab/ticket" in text
    assert "_tickets" in text
