"""
Tests for authentication endpoints.
"""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
class TestAuthRouter:
    """Test cases for /api/auth endpoints."""

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
