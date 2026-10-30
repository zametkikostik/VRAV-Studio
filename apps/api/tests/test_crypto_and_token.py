from app.services.crypto import encrypt_secret, decrypt_secret, key_hint
from app.services.license_token import issue_offline_token, verify_offline_token


def test_encrypt_decrypt_roundtrip():
    token = encrypt_secret("sk-test-secret-key-value")
    assert isinstance(token, bytes)
    assert decrypt_secret(token) == "sk-test-secret-key-value"


def test_key_hint():
    assert "…" in key_hint("sk-abcdefghijklmnop")
    assert key_hint("short") == "****"


def test_offline_license_token():
    tok = issue_offline_token(
        license_key="VRAV-AAAA-BBBB-CCCC-DDDD",
        license_id="00000000-0000-0000-0000-000000000001",
        max_installations=2,
        features={"desktop": True},
        ttl_days=7,
    )
    claims = verify_offline_token(tok)
    assert claims is not None
    assert claims["sub"] == "VRAV-AAAA-BBBB-CCCC-DDDD"
