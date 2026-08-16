# Authentication System - Knowledge OS

This document describes the JWT-based authentication system implemented for Knowledge OS.

## Overview

The authentication system provides:
- User registration with email/username
- JWT-based authentication (access + refresh tokens)
- Password hashing with bcrypt
- Password reset flow
- Protected routes/endpoints
- Session persistence across page reloads

## Backend (FastAPI)

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `JWT_SECRET_KEY` | Secret key for signing JWT tokens | Persisted to `<data_dir>/.jwt_secret` if unset |
| `JWT_SECRET_FILE` | Override path for the persisted dev secret | `<data_dir>/.jwt_secret` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access token expiry | `1440` (24 hours) |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Refresh token expiry | `7` (days) |
| `RESET_TOKEN_EXPIRE_HOURS` | Password reset token expiry | `1` (hour) |

**Important**: In production, `JWT_SECRET_KEY` is **required**. The backend
refuses to start if it's unset and `DEBUG` is not `true`. In development,
if `JWT_SECRET_KEY` is unset the service generates a 64-byte URL-safe
secret and persists it to `<data_dir>/.jwt_secret` so tokens survive
restarts. If that file write ever fails the secret falls back to an
ephemeral one (and an explicit error is logged) — sessions will not
survive restarts in that mode.

### API Endpoints

All endpoints are prefixed with `/api/v1/auth`.

#### POST `/api/v1/auth/register`
Register a new user account.

**Request:**
```json
{
  "email": "user@example.com",
  "username": "johndoe",
  "display_name": "John Doe",  // optional
  "password": "securepassword123"
}
```

**Response:** `TokenResponse`
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "token_type": "bearer",
  "expires_in": 86400,
  "user": {
    "id": "uuid",
    "email": "user@example.com",
    "username": "johndoe",
    "display_name": "John Doe",
    "is_active": true,
    "created_at": "2024-01-01T00:00:00Z"
  }
}
```

#### POST `/api/v1/auth/login`
Login with email and password.

**Request:**
```json
{
  "email": "user@example.com",
  "password": "securepassword123"
}
```

**Response:** `TokenResponse` (same as register)

#### POST `/api/v1/auth/refresh`
Refresh an access token using a refresh token.

**Request:**
```json
{
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGc..."
}
```

**Response:** `TokenResponse` (same as register)

#### POST `/api/v1/auth/logout`
Logout by invalidating the refresh token.

**Request:**
```json
{
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGc..."
}
```

**Response:**
```json
{
  "message": "Successfully logged out"
}
```

#### GET `/api/v1/auth/me`
Get the current authenticated user's profile.

**Headers:** `Authorization: Bearer <access_token>`

**Response:** `UserResponse`
```json
{
  "id": "uuid",
  "email": "user@example.com",
  "username": "johndoe",
  "display_name": "John Doe",
  "is_active": true,
  "created_at": "2024-01-01T00:00:00Z"
}
```

#### POST `/api/v1/auth/password-reset`
Request a password reset email.

**Request:**
```json
{
  "email": "user@example.com"
}
```

**Response:**
```json
{
  "message": "If an account with this email exists, a password reset token has been sent"
}
```

> The endpoint never returns the reset token in the response body — even in
> development. Tokens are delivered via the configured email transport (or
> the application log if SMTP is not configured). This avoids accidental
> token leaks via shared HAR files / dev tools.

#### POST `/api/v1/auth/password-reset/confirm`
Confirm a password reset with the token.

**Request:**
```json
{
  "token": "reset-token-uuid",
  "new_password": "newpassword123"
}
```

**Response:**
```json
{
  "message": "Password has been reset successfully"
}
```

### Protected Routes

To protect a route, use the `get_current_user` dependency:

```python
from app.middleware.auth import get_current_user
from fastapi import Depends

@router.get("/protected")
async def protected_route(current_user: dict = Depends(get_current_user)):
    return {"message": f"Hello {current_user['username']}"}
```

### Database Tables

#### `users`
| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT (UUID) | Primary key |
| `email` | TEXT | Unique, indexed |
| `username` | TEXT | Unique, indexed |
| `display_name` | TEXT | Optional display name |
| `hashed_password` | TEXT | Bcrypt hash |
| `is_active` | INTEGER | Active status (0/1) |
| `created_at` | TIMESTAMP | Creation time |
| `updated_at` | TIMESTAMP | Last update |

#### `refresh_tokens`
| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT (UUID) | Primary key |
| `user_id` | TEXT | Foreign key → users |
| `token_hash` | TEXT | Hashed refresh token |
| `expires_at` | TIMESTAMP | Expiration time |
| `created_at` | TIMESTAMP | Creation time |

#### `password_reset_tokens`
| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT (UUID) | Primary key |
| `user_id` | TEXT | Foreign key → users |
| `token_hash` | TEXT | Hashed reset token |
| `expires_at` | TIMESTAMP | Expiration time |
| `used` | INTEGER | Token used status (0/1) |
| `created_at` | TIMESTAMP | Creation time |

## Frontend (React + TypeScript)

### Auth Store (Zustand)

The `useAuthStore` provides authentication state and actions:

```typescript
import { useAuthStore } from '@/stores/auth'

const {
  user,
  isAuthenticated,
  isLoading,
  error,
  login,
  register,
  logout,
  refreshUser,
  clearError
} = useAuthStore()
```

**State:**
- `user: User | null` - Current user object
- `isAuthenticated: boolean` - Auth status
- `isLoading: boolean` - Loading state
- `error: string | null` - Error message

**Actions:**
- `login(email, password)` - Login user
- `register(data)` - Register new user
- `logout()` - Logout and clear tokens
- `refreshUser()` - Fetch current user from API
- `clearError()` - Clear error message

### API Client

The auth API is available via `authApi`:

```typescript
import { authApi } from '@/services/api'

// Login
const response = await authApi.login(email, password)

// Register
const response = await authApi.register({
  email,
  username,
  password,
  display_name
})

// Logout
await authApi.logout(refreshToken)

// Get current user
const user = await authApi.getMe()

// Password reset
await authApi.requestPasswordReset(email)
await authApi.confirmPasswordReset(token, newPassword)
```

### Protected Routes

Use the `<ProtectedRoute>` component to protect routes:

```tsx
import { ProtectedRoute } from '@/components/auth/ProtectedRoute'

<Route
  path="/protected"
  element={
    <ProtectedRoute>
      <MyProtectedPage />
    </ProtectedRoute>
  }
/>
```

### Token Management

Tokens are automatically:
- Stored in `localStorage` (`access_token`, `refresh_token`)
- Attached to API requests via axios interceptor
- Refreshed automatically on 401 responses
- Cleared on logout

## Security Considerations

1. **JWT Secret**: `JWT_SECRET_KEY` is required in production — backend
   refuses to start without it (unless `DEBUG=true`).
2. **HTTPS**: Use HTTPS in production to protect tokens in transit.
3. **Token expiry**: Access 24h, refresh 7d, reset 1h by default; tune via
   env vars.
4. **Refresh tokens** are stored as HMAC-SHA-256 hashes (not bcrypt — JWTs
   are too long for bcrypt's 72-byte input limit). Legacy bcrypt-hashed
   tokens are still verified for graceful rollover. Revocation works by
   deleting the hash row.
5. **Token rotation**: each access token includes a `jti` claim so two
   tokens issued in the same second are distinct.
6. **Password hashing**: bcrypt via `passlib`.
7. **Rate limiting**: The auth endpoint group has stricter limits
   (`5/minute`). The user-keyed limiter binds bad / expired tokens to
   `(client_ip, sha256(token)[:16])` so an attacker rotating IPs while
   reusing malformed tokens cannot dodge per-user caps. See
   [SECURITY.md](SECURITY.md) for the per-process limiter caveat.
8. **Tokens in localStorage**: the SPA stores access + refresh tokens in
   `localStorage` for cross-tab persistence. This is XSS-exposed — the
   bleach-based content sanitizer + nginx CSP are the primary mitigations.
   Move to HttpOnly refresh cookies if you operate in a hostile
   environment.

## Development Setup

1. Install backend dependencies:
```bash
cd backend
pip install -r requirements.txt
```

2. The SQLite database tables will be created automatically on first run.

3. Start the backend server:
```bash
uvicorn app.main:app --reload
```

4. Install frontend dependencies:
```bash
cd frontend
npm install
```

5. Start the frontend dev server:
```bash
npm run dev
```

6. Navigate to `http://localhost:5173/login` to register/login.

## Testing

The auth flow has dedicated coverage:

- `backend/tests/test_auth.py`, `test_auth_integration.py` — unit and
  integration tests for register / login / refresh / logout / password
  reset / `/auth/me`.
- `backend/tests/test_rate_limiter.py` — verifies the per-user keying
  including the bad-token fingerprint binding.
- `e2e/specs/00-anonymous/auth.spec.ts` — Playwright walks the register,
  login, and reset-password flows in the real browser.
- `e2e/specs/90-api/api-health.spec.ts` — verifies an unauthenticated read
  of a protected endpoint returns 401, plus the agent-id traversal
  regression.

Reset tokens are not returned in the API response. To test the reset flow
without a real SMTP server, point `LOG_LEVEL=DEBUG` and inspect the
backend log — the token is logged so you can complete the flow locally.

## Source layout

| Layer | Path |
|---|---|
| Models | `backend/app/models/user.py` |
| Service | `backend/app/services/auth.py` |
| Router | `backend/app/routers/auth.py` |
| Middleware | `backend/app/middleware/auth.py`, `backend/app/middleware/rate_limit.py` |
| Migrations | `backend/alembic/versions/0001_baseline_schema.py` |
| Frontend store | `frontend/src/stores/auth.ts` |
| Login UI | `frontend/src/pages/LoginPage.tsx` |
| Reset UI | `frontend/src/pages/ResetPasswordPage.tsx` |
| Route guard | `frontend/src/components/auth/ProtectedRoute.tsx` |
| API client | `frontend/src/services/api.ts` (`authApi`) |
