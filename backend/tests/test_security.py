from app.security import hash_password, verify_password


def test_password_hash_uses_argon2id_and_verifies():
    password = "correct-horse-battery-staple"
    encoded = hash_password(password)
    assert encoded.startswith("$argon2id$")
    assert verify_password(password, encoded)
    assert not verify_password("incorrect-password", encoded)
