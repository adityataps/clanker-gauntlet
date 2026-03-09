"""
Integration tests for auth endpoints.

Uses `http_client` (no DB session override) so each request gets its own
connection — avoids asyncpg concurrent-operation errors.
`clean_users` truncates the users table after each test class.

Requires: PostgreSQL running with clanker_gauntlet_test DB.
"""

import pytest


@pytest.fixture
async def registered_user(http_client):
    """Register a user and return (email, password, token)."""
    email = "testuser@example.com"
    password = "securepassword123"
    resp = await http_client.post(
        "/auth/register",
        json={"email": email, "password": password, "display_name": "Test User"},
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return email, password, token


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("clean_users")
class TestRegister:
    async def test_register_success(self, http_client):
        resp = await http_client.post(
            "/auth/register",
            json={
                "email": "new@example.com",
                "password": "password123",
                "display_name": "New User",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    async def test_register_duplicate_email(self, http_client):
        payload = {
            "email": "duplicate@example.com",
            "password": "password123",
            "display_name": "User",
        }
        r1 = await http_client.post("/auth/register", json=payload)
        assert r1.status_code == 200
        resp = await http_client.post("/auth/register", json=payload)
        assert resp.status_code == 409

    async def test_register_invalid_email(self, http_client):
        resp = await http_client.post(
            "/auth/register",
            json={"email": "not-an-email", "password": "password123", "display_name": "User"},
        )
        assert resp.status_code == 422

    async def test_register_missing_fields(self, http_client):
        resp = await http_client.post("/auth/register", json={"email": "a@b.com"})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("clean_users")
class TestLogin:
    async def test_login_success(self, http_client, registered_user):
        email, password, _ = registered_user
        resp = await http_client.post("/auth/login", json={"email": email, "password": password})
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    async def test_login_wrong_password(self, http_client, registered_user):
        email, _, _ = registered_user
        resp = await http_client.post(
            "/auth/login", json={"email": email, "password": "wrongpassword"}
        )
        assert resp.status_code == 401

    async def test_login_unknown_email(self, http_client):
        resp = await http_client.post(
            "/auth/login",
            json={"email": "nobody@example.com", "password": "password123"},
        )
        assert resp.status_code == 401

    async def test_login_invalid_email_format(self, http_client):
        resp = await http_client.post(
            "/auth/login", json={"email": "notanemail", "password": "password123"}
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# /auth/me
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("clean_users")
class TestMe:
    async def test_me_success(self, http_client, registered_user):
        email, _, token = registered_user
        resp = await http_client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == email
        assert data["display_name"] == "Test User"
        assert data["has_anthropic_key"] is False

    async def test_me_no_token(self, http_client):
        resp = await http_client.get("/auth/me")
        assert resp.status_code in (401, 403)  # FastAPI HTTPBearer varies by version

    async def test_me_invalid_token(self, http_client):
        resp = await http_client.get(
            "/auth/me", headers={"Authorization": "Bearer invalid.token.here"}
        )
        assert resp.status_code == 401

    async def test_me_malformed_header(self, http_client):
        resp = await http_client.get("/auth/me", headers={"Authorization": "NotBearer token"})
        assert resp.status_code in (401, 403)  # FastAPI HTTPBearer varies by version
