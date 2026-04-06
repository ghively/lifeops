"""
Tests for authentication endpoints.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import jwt
import pytest

from app.middleware.auth import get_current_user, get_optional_user
from app.services.auth import auth_service


def _user_payload(
    user_id: str = "user-123",
    email: str = "user@example.com",
    username: str = "testuser",
    display_name: str = "Test User",
):
    now = datetime.now(timezone.utc)
    return {
        "id": user_id,
        "email": email,
        "username": username,
        "display_name": display_name,
        "is_active": True,
        "created_at": now,
        "updated_at": now,
    }


def _assert_token_response(data: dict, expected_user: dict):
    assert data["access_token"]
    assert data["refresh_token"]
    assert data["token_type"] == "bearer"
    assert data["expires_in"] == auth_service.access_token_expire_minutes * 60
    assert data["user"]["id"] == expected_user["id"]
    assert data["user"]["email"] == expected_user["email"]
    assert data["user"]["username"] == expected_user["username"]


@pytest.mark.asyncio
class TestAuthRouter:
    """Test cases for /api/auth endpoints."""

    async def test_register_success(self, test_client):
        user = _user_payload()
        register_data = {
            "email": user["email"],
            "username": user["username"],
            "display_name": user["display_name"],
            "password": "Password123!",
        }

        with patch(
            "app.routers.auth.auth_service.create_user",
            AsyncMock(return_value=user),
        ), patch(
            "app.routers.auth.auth_service.store_refresh_token",
            AsyncMock(return_value="refresh-token-id"),
        ):
            response = await test_client.post("/api/v1/auth/register", json=register_data)

        assert response.status_code == 201
        _assert_token_response(response.json(), user)

    async def test_register_duplicate(self, test_client):
        user = _user_payload(
            user_id="duplicate-user-id",
            email="duplicate@example.com",
            username="duplicate-user",
            display_name="Duplicate User",
        )
        register_data = {
            "email": user["email"],
            "username": user["username"],
            "display_name": user["display_name"],
            "password": "Password123!",
        }

        with patch(
            "app.routers.auth.auth_service.create_user",
            AsyncMock(side_effect=[user, ValueError("Email already registered")]),
        ), patch(
            "app.routers.auth.auth_service.store_refresh_token",
            AsyncMock(return_value="refresh-token-id"),
        ):
            first_response = await test_client.post("/api/v1/auth/register", json=register_data)
            second_response = await test_client.post("/api/v1/auth/register", json=register_data)

        assert first_response.status_code == 201
        _assert_token_response(first_response.json(), user)
        assert second_response.status_code == 400
        assert second_response.json()["detail"] == "Email already registered"

    async def test_login_success(self, test_client):
        user = _user_payload(email="login@example.com", username="login-user")

        with patch(
            "app.routers.auth.auth_service.authenticate_user",
            AsyncMock(return_value=user),
        ), patch(
            "app.routers.auth.auth_service.store_refresh_token",
            AsyncMock(return_value="refresh-token-id"),
        ):
            response = await test_client.post(
                "/api/v1/auth/login",
                json={"email": user["email"], "password": "Password123!"},
            )

        assert response.status_code == 200
        _assert_token_response(response.json(), user)

    async def test_login_invalid_credentials(self, test_client):
        with patch(
            "app.routers.auth.auth_service.authenticate_user",
            AsyncMock(return_value=None),
        ):
            response = await test_client.post(
                "/api/v1/auth/login",
                json={"email": "user@example.com", "password": "wrong-password"},
            )

        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid email or password"

    async def test_login_missing_fields(self, test_client):
        response = await test_client.post(
            "/api/v1/auth/login",
            json={"password": "Password123!"},
        )

        assert response.status_code == 422
        detail = response.json()["detail"]
        assert any(item["loc"][-1] == "email" for item in detail)

    async def test_unauthenticated_access(self, test_client):
        from app.main import app

        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_optional_user, None)

        response = await test_client.get("/api/v1/objects")

        assert response.status_code == 401
        assert response.json()["detail"] == "Missing authentication token"

    async def test_authenticated_access(self, test_client):
        from app.main import app

        user = _user_payload(user_id="auth-user", email="auth@example.com", username="auth-user")
        token = auth_service.create_access_token(user["id"])

        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_optional_user, None)

        with patch(
            "app.middleware.auth.auth_service.get_user_by_id",
            AsyncMock(return_value=user),
        ):
            response = await test_client.get(
                "/api/v1/objects",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 200
        data = response.json()
        assert "objects" in data

    async def test_refresh_token(self, test_client):
        user = _user_payload(user_id="refresh-user", email="refresh@example.com", username="refresh-user")
        refresh_token = auth_service.create_refresh_token(user["id"])

        with patch(
            "app.routers.auth.auth_service.validate_refresh_token",
            AsyncMock(return_value=True),
        ), patch(
            "app.routers.auth.auth_service.get_user_by_id",
            AsyncMock(return_value=user),
        ):
            response = await test_client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": refresh_token},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["refresh_token"] is not None
        assert data["user"]["id"] == user["id"]
        assert data["access_token"]

    async def test_token_expiry(self, test_client):
        from app.main import app

        expired_token = jwt.encode(
            {
                "sub": "expired-user",
                "type": "access",
                "iat": datetime.utcnow() - timedelta(hours=2),
                "exp": datetime.utcnow() - timedelta(hours=1),
            },
            auth_service.secret_key,
            algorithm="HS256",
        )

        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_optional_user, None)

        response = await test_client.get(
            "/api/v1/objects",
            headers={"Authorization": f"Bearer {expired_token}"},
        )

        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid authentication token"

    async def test_password_reset_does_not_return_dev_token(self, test_client):
        """Password reset responses must not leak reset tokens."""
        with patch(
            "app.routers.auth.auth_service.create_password_reset_token",
            AsyncMock(return_value="secret-reset-token"),
        ):
            response = await test_client.post(
                "/api/v1/auth/password-reset",
                json={"email": "user@example.com"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["message"]
        assert "_dev_token" not in data
