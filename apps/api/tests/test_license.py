from app.services.license_keys import generate_license_key


def test_generate_license_key_format():
    key = generate_license_key()
    assert key.startswith("VRAV-")
    parts = key.split("-")
    assert len(parts) == 5
    for p in parts[1:]:
        assert len(p) == 4
        assert p.isalnum()
        assert p == p.upper()


def test_keys_are_unique_enough():
    keys = {generate_license_key() for _ in range(50)}
    assert len(keys) == 50
