"""Unit tests for security utilities (no DB/Redis required)."""
import time

import jwt
import pytest

from app.core import security
from app.core.config import settings


def test_password_hash_roundtrip():
    h = security.hash_password("s3cret-pw")
    assert h != "s3cret-pw"
    assert security.verify_password("s3cret-pw", h) is True
    assert security.verify_password("wrong", h) is False


def test_password_too_long_rejected():
    with pytest.raises(ValueError):
        security.hash_password("x" * 73)


def test_verify_handles_garbage_hash():
    assert security.verify_password("whatever", "not-a-bcrypt-hash") is False


def test_access_token_roundtrip():
    token, expires_in = security.create_access_token(user_id="u-1", role="admin")
    assert expires_in == settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    claims = security.decode_token(token)
    assert claims["sub"] == "u-1"
    assert claims["role"] == "admin"
    assert "jti" in claims and "exp" in claims and "iat" in claims


def test_decode_tampered_token_raises():
    token, _ = security.create_access_token(user_id="u-1", role="admin")
    with pytest.raises(security.TokenError):
        security.decode_token(token + "x")


def test_decode_expired_token_raises():
    expired = jwt.encode(
        {"sub": "u-1", "role": "admin", "jti": "j", "iat": int(time.time()) - 100,
         "exp": int(time.time()) - 10},
        settings.SECRET_KEY,
        algorithm="HS256",
    )
    with pytest.raises(security.TokenError):
        security.decode_token(expired)


def test_decode_wrong_signature_raises():
    bad = jwt.encode({"sub": "u-1", "exp": int(time.time()) + 60}, "different-secret", algorithm="HS256")
    with pytest.raises(security.TokenError):
        security.decode_token(bad)
