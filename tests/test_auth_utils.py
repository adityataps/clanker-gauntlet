"""
Unit tests for auth utilities: JWT and Fernet crypto.
No DB or network required.
"""

import uuid

import pytest
from authlib.jose import JoseError

from backend.auth.crypto import decrypt_api_key, encrypt_api_key
from backend.auth.jwt import create_access_token, decode_access_token

# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------


class TestJWT:
    def test_round_trip(self):
        user_id = str(uuid.uuid4())
        token = create_access_token(user_id)
        claims = decode_access_token(token)
        assert claims["sub"] == user_id

    def test_extra_claims_preserved(self):
        user_id = str(uuid.uuid4())
        token = create_access_token(user_id, extra_claims={"email": "test@example.com"})
        claims = decode_access_token(token)
        assert claims["email"] == "test@example.com"

    def test_invalid_token_raises(self):
        with pytest.raises(JoseError):
            decode_access_token("not.a.valid.token")

    def test_tampered_token_raises(self):
        token = create_access_token(str(uuid.uuid4()))
        tampered = token[:-4] + "xxxx"
        with pytest.raises(JoseError):
            decode_access_token(tampered)

    def test_token_has_exp(self):
        token = create_access_token(str(uuid.uuid4()))
        claims = decode_access_token(token)
        assert "exp" in claims
        assert "iat" in claims

    def test_returns_string(self):
        token = create_access_token(str(uuid.uuid4()))
        assert isinstance(token, str)
        assert len(token) > 0


# ---------------------------------------------------------------------------
# Fernet crypto
# ---------------------------------------------------------------------------


class TestCrypto:
    def test_round_trip(self):
        plaintext = "sk-ant-test-api-key-12345"
        ciphertext = encrypt_api_key(plaintext)
        assert decrypt_api_key(ciphertext) == plaintext

    def test_ciphertext_is_bytes(self):
        ciphertext = encrypt_api_key("test-key")
        assert isinstance(ciphertext, bytes)

    def test_different_plaintexts_produce_different_ciphertexts(self):
        ct1 = encrypt_api_key("key-one")
        ct2 = encrypt_api_key("key-two")
        assert ct1 != ct2

    def test_same_plaintext_produces_different_ciphertexts(self):
        # Fernet uses random IV — same plaintext should not produce same bytes
        ct1 = encrypt_api_key("same-key")
        ct2 = encrypt_api_key("same-key")
        assert ct1 != ct2

    def test_both_decrypt_to_same_value(self):
        ct1 = encrypt_api_key("same-key")
        ct2 = encrypt_api_key("same-key")
        assert decrypt_api_key(ct1) == decrypt_api_key(ct2) == "same-key"

    def test_corrupt_ciphertext_raises(self):
        with pytest.raises(ValueError, match="Failed to decrypt"):
            decrypt_api_key(b"this-is-not-valid-fernet-ciphertext")

    def test_empty_string_round_trip(self):
        ciphertext = encrypt_api_key("")
        assert decrypt_api_key(ciphertext) == ""
