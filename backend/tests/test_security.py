import bcrypt

from app.core.security import (
    create_refresh_token,
    decode_token,
    hash_password,
    needs_password_rehash,
    verify_password,
)


def test_new_passwords_use_argon2_and_verify():
    hashed = hash_password("a-long-test-password")
    assert hashed.startswith("$argon2")
    assert verify_password("a-long-test-password", hashed)
    assert not verify_password("wrong-password", hashed)
    assert not needs_password_rehash(hashed)


def test_legacy_bcrypt_passwords_remain_compatible():
    hashed = bcrypt.hashpw(b"legacy-password", bcrypt.gensalt()).decode()
    assert verify_password("legacy-password", hashed)
    assert needs_password_rehash(hashed)


def test_refresh_token_contains_rotation_identifier():
    token = create_refresh_token({"sub": "user-id"}, jti="session-id")
    payload = decode_token(token)
    assert payload["type"] == "refresh"
    assert payload["jti"] == "session-id"

