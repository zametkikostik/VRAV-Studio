import pytest
from pydantic import ValidationError

from app.schemas.auth import RegisterRequest


def test_register_valid():
    r = RegisterRequest(email="User@Example.com", password="password1", full_name="Test")
    assert r.email.lower() == "user@example.com"
    assert r.password == "password1"


def test_register_short_password():
    with pytest.raises(ValidationError):
        RegisterRequest(email="a@b.co", password="short")
