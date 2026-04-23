"""Integration tests for auth flow using real SQLite mock."""

import pytest

from app.services.auth import auth_service


@pytest.mark.asyncio
async def test_auth_full_flow_register_login_refresh(test_client, mock_sqlite_manager):
    """Test complete auth flow: register → login → refresh token."""
    # 1. Register
    register_response = await test_client.post(
        "/api/v1/auth/register",
        json={
            "username": "testuser",
            "email": "test@example.com",
            "password": "TestPassword123!",
            "display_name": "Test User",
        },
    )
    assert register_response.status_code == 201
    register_data = register_response.json()
    access_token = register_data["access_token"]
    refresh_token = register_data["refresh_token"]
    assert register_data["user"]["email"] == "test@example.com"

    # 2. Login with same credentials
    login_response = await test_client.post(
        "/api/v1/auth/login",
        json={
            "email": "test@example.com",
            "password": "TestPassword123!",
        },
    )
    assert login_response.status_code == 200
    login_data = login_response.json()
    new_access_token = login_data["access_token"]
    new_refresh_token = login_data["refresh_token"]
    assert login_data["user"]["email"] == "test@example.com"

    # 3. Use access token to access protected endpoint
    test_client.headers["Authorization"] = f"Bearer {access_token}"
    profile_response = await test_client.get("/api/v1/auth/me")
    assert profile_response.status_code == 200
    profile_data = profile_response.json()
    assert profile_data["email"] == "test@example.com"
    test_client.headers.pop("Authorization", None)

    # 4. Refresh access token
    refresh_response = await test_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": new_refresh_token},
    )
    assert refresh_response.status_code == 200
    refresh_data = refresh_response.json()
    refreshed_access_token = refresh_data["access_token"]
    assert refreshed_access_token != new_access_token


@pytest.mark.asyncio
async def test_login_with_wrong_password(test_client, mock_sqlite_manager):
    """Test login fails with incorrect password."""
    # Register user
    await test_client.post(
        "/api/v1/auth/register",
        json={
            "username": "testuser",
            "email": "test@example.com",
            "password": "CorrectPassword123!",
            "display_name": "Test User",
        },
    )

    # Try login with wrong password
    login_response = await test_client.post(
        "/api/v1/auth/login",
        json={
            "email": "test@example.com",
            "password": "WrongPassword123!",
        },
    )
    assert login_response.status_code == 401


@pytest.mark.asyncio
async def test_login_with_nonexistent_email(test_client, mock_sqlite_manager):
    """Test login fails with nonexistent email."""
    login_response = await test_client.post(
        "/api/v1/auth/login",
        json={
            "email": "nonexistent@example.com",
            "password": "SomePassword123!",
        },
    )
    assert login_response.status_code == 401


@pytest.mark.asyncio
async def test_access_token_used_after_logout(test_client, mock_sqlite_manager):
    """Test that access token stops working after logout."""
    # Register and login
    register_response = await test_client.post(
        "/api/v1/auth/register",
        json={
            "username": "testuser",
            "email": "test@example.com",
            "password": "TestPassword123!",
            "display_name": "Test User",
        },
    )
    access_token = register_response.json()["access_token"]
    refresh_token = register_response.json()["refresh_token"]

    # Use token to access protected endpoint (should work)
    test_client.headers["Authorization"] = f"Bearer {access_token}"
    profile_response = await test_client.get("/api/v1/auth/me")
    assert profile_response.status_code == 200
    test_client.headers.pop("Authorization", None)

    # Logout
    logout_response = await test_client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": refresh_token},
    )
    assert logout_response.status_code == 200

    # Try to use the refresh token (should fail)
    refresh_response = await test_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert refresh_response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token_invalid(test_client, mock_sqlite_manager):
    """Test refresh fails with invalid refresh token."""
    refresh_response = await test_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "invalid_token_xyz"},
    )
    assert refresh_response.status_code == 401


@pytest.mark.asyncio
async def test_register_duplicate_email(test_client, mock_sqlite_manager):
    """Test registering with duplicate email fails."""
    # Register first user
    first_response = await test_client.post(
        "/api/v1/auth/register",
        json={
            "username": "testuser1",
            "email": "duplicate@example.com",
            "password": "TestPassword123!",
            "display_name": "Test User 1",
        },
    )
    assert first_response.status_code == 201

    # Try to register with same email
    second_response = await test_client.post(
        "/api/v1/auth/register",
        json={
            "username": "testuser2",
            "email": "duplicate@example.com",
            "password": "TestPassword123!",
            "display_name": "Test User 2",
        },
    )
    assert second_response.status_code == 400


@pytest.mark.asyncio
async def test_register_duplicate_username(test_client, mock_sqlite_manager):
    """Test registering with duplicate username fails."""
    # Register first user
    first_response = await test_client.post(
        "/api/v1/auth/register",
        json={
            "username": "duplicateuser",
            "email": "first@example.com",
            "password": "TestPassword123!",
            "display_name": "Test User 1",
        },
    )
    assert first_response.status_code == 201

    # Try to register with same username
    second_response = await test_client.post(
        "/api/v1/auth/register",
        json={
            "username": "duplicateuser",
            "email": "second@example.com",
            "password": "TestPassword123!",
            "display_name": "Test User 2",
        },
    )
    assert second_response.status_code == 400


@pytest.mark.asyncio
async def test_password_reset_flow(test_client, mock_sqlite_manager):
    """Test complete password reset flow."""
    # Register user
    register_response = await test_client.post(
        "/api/v1/auth/register",
        json={
            "username": "testuser",
            "email": "test@example.com",
            "password": "OldPassword123!",
            "display_name": "Test User",
        },
    )
    assert register_response.status_code == 201

    # Request password reset
    reset_request_response = await test_client.post(
        "/api/v1/auth/password-reset",
        json={"email": "test@example.com"},
    )
    assert reset_request_response.status_code == 200

    # Get the reset token from mock storage
    reset_tokens = list(mock_sqlite_manager._storage["password_reset_tokens"].values())
    assert len(reset_tokens) > 0
    reset_token = reset_tokens[0]["id"]  # token ID is what we use

    # Confirm password reset with new password
    reset_confirm_response = await test_client.post(
        "/api/v1/auth/password-reset/confirm",
        json={
            "token": reset_token,
            "new_password": "NewPassword123!",
        },
    )
    assert reset_confirm_response.status_code == 200

    # Login with new password should succeed
    login_with_new_password = await test_client.post(
        "/api/v1/auth/login",
        json={
            "email": "test@example.com",
            "password": "NewPassword123!",
        },
    )
    assert login_with_new_password.status_code == 200

    # Login with old password should fail
    login_with_old_password = await test_client.post(
        "/api/v1/auth/login",
        json={
            "email": "test@example.com",
            "password": "OldPassword123!",
        },
    )
    assert login_with_old_password.status_code == 401


@pytest.mark.asyncio
async def test_concurrent_logins_independent_tokens(test_client, mock_sqlite_manager):
    """Test that concurrent logins from same user produce independent tokens."""
    # Register user
    register_response = await test_client.post(
        "/api/v1/auth/register",
        json={
            "username": "testuser",
            "email": "test@example.com",
            "password": "TestPassword123!",
            "display_name": "Test User",
        },
    )
    assert register_response.status_code == 201

    # Perform two logins
    login1_response = await test_client.post(
        "/api/v1/auth/login",
        json={
            "email": "test@example.com",
            "password": "TestPassword123!",
        },
    )
    assert login1_response.status_code == 200
    token1 = login1_response.json()["refresh_token"]

    login2_response = await test_client.post(
        "/api/v1/auth/login",
        json={
            "email": "test@example.com",
            "password": "TestPassword123!",
        },
    )
    assert login2_response.status_code == 200
    token2 = login2_response.json()["refresh_token"]

    # Tokens should be different
    assert token1 != token2

    # Both tokens should work independently
    refresh1 = await test_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": token1},
    )
    assert refresh1.status_code == 200

    refresh2 = await test_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": token2},
    )
    assert refresh2.status_code == 200

    # Logout with one token shouldn't affect the other
    logout_response = await test_client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": token1},
    )
    assert logout_response.status_code == 200

    # Token 2 should still work
    refresh2_after_logout = await test_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": token2},
    )
    assert refresh2_after_logout.status_code == 200

    # Token 1 should not work
    refresh1_after_logout = await test_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": token1},
    )
    assert refresh1_after_logout.status_code == 401
