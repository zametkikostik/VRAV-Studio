from app.core.security import create_access_token, decode_access_token, hash_password, verify_password


def test_hash_and_verify():
    h = hash_password("secret123")
    assert h != "secret123"
    assert verify_password("secret123", h)
    assert not verify_password("wrong", h)


def test_jwt_roundtrip():
    token = create_access_token("user-uuid-123")
    assert decode_access_token(token) == "user-uuid-123"
    assert decode_access_token("garbage") is None
