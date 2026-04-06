"""Authentication Service - JWT tokens and password management"""
import uuid
import logging
import os
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any

import jwt
from passlib.context import CryptContext

from app.config import settings
from app.database.sqlite import sqlite_manager

logger = logging.getLogger(__name__)

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:
    """Service for authentication operations"""

    def __init__(self):
        self.secret_key = getattr(settings, 'secret_key', None)
        self.secret_source = "environment"
        self.secret_file_path: Path | None = None
        self._secret_warning_logged = False
        if not self.secret_key:
            self.secret_key = self._load_or_create_persisted_secret()
        if os.getenv("DEBUG") != "true" and not os.getenv("JWT_SECRET_KEY"):
            logger.warning(
                "SECURITY: JWT_SECRET_KEY not set in environment. Using persisted file secret. "
                "This is insecure for multi-replica production deployments."
            )

        self.access_token_expire_minutes = getattr(settings, 'access_token_expire_minutes', 1440)  # 24h default
        self.refresh_token_expire_days = getattr(settings, 'refresh_token_expire_days', 7)  # 7 days default
        self.reset_token_expire_hours = getattr(settings, 'reset_token_expire_hours', 1)  # 1 hour default

    def _resolve_secret_file_path(self) -> Path:
        configured_path = os.getenv("JWT_SECRET_FILE")
        if configured_path:
            return Path(configured_path)

        database_url = getattr(settings, "database_url", "")
        if database_url.startswith("sqlite:///"):
            return Path(database_url.removeprefix("sqlite:///")).resolve().parent / ".jwt_secret"

        return Path(getattr(settings, "data_dir")).resolve() / ".jwt_secret"

    def _load_or_create_persisted_secret(self) -> str:
        secret_path = self._resolve_secret_file_path()
        self.secret_file_path = secret_path

        try:
            if secret_path.exists():
                persisted_secret = secret_path.read_text(encoding="utf-8").strip()
                if persisted_secret:
                    self.secret_source = "persisted-file"
                    return persisted_secret

            secret_path.parent.mkdir(parents=True, exist_ok=True)
            persisted_secret = secrets.token_urlsafe(64)
            secret_path.write_text(f"{persisted_secret}\n", encoding="utf-8")
            self.secret_source = "persisted-file"
            logger.warning("Persisted generated JWT secret to %s", secret_path)
            return persisted_secret
        except Exception:
            self.secret_source = "ephemeral-fallback"
            logger.exception("Failed to persist JWT secret at %s; falling back to an ephemeral secret", secret_path)
            return secrets.token_urlsafe(64)

    def log_secret_configuration_warning(self) -> None:
        if self._secret_warning_logged or self.secret_source == "environment":
            return

        location = str(self.secret_file_path) if self.secret_file_path else "<unavailable>"
        logger.warning("JWT_SECRET_KEY is not set. Backend is using a persisted fallback secret from %s", location)
        logger.warning("Production warning: configure JWT_SECRET_KEY from your environment or secret manager before deployment")
        if self.secret_source == "ephemeral-fallback":
            logger.error("JWT secret persistence failed. Existing sessions will be invalidated on restart until secret storage works")
        self._secret_warning_logged = True

    def hash_password(self, password: str) -> str:
        """Hash a password using bcrypt"""
        return pwd_context.hash(password)

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against a hash"""
        return pwd_context.verify(plain_password, hashed_password)

    def create_access_token(self, user_id: str, additional_claims: Optional[Dict[str, Any]] = None) -> str:
        """Create a JWT access token"""
        claims = {
            "sub": user_id,
            "type": "access",
            "iat": datetime.utcnow(),
            "exp": datetime.utcnow() + timedelta(minutes=self.access_token_expire_minutes),
        }
        if additional_claims:
            claims.update(additional_claims)
        return jwt.encode(claims, self.secret_key, algorithm="HS256")

    def create_refresh_token(self, user_id: str) -> str:
        """Create a JWT refresh token"""
        claims = {
            "sub": user_id,
            "type": "refresh",
            "iat": datetime.utcnow(),
            "exp": datetime.utcnow() + timedelta(days=self.refresh_token_expire_days),
            "jti": str(uuid.uuid4()),  # Unique identifier for the token
        }
        return jwt.encode(claims, self.secret_key, algorithm="HS256")

    def decode_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Decode and validate a JWT token"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=["HS256"])
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("Token has expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
            return None

    async def create_user(self, email: str, username: str, password: str, display_name: Optional[str] = None) -> Dict[str, Any]:
        """Create a new user"""
        # Check if user already exists
        existing = await sqlite_manager.fetchone(
            "SELECT id, email, username FROM users WHERE email = ? OR username = ?",
            (email, username)
        )
        if existing:
            if existing["email"] == email:
                raise ValueError("Email already registered")
            if existing["username"] == username:
                raise ValueError("Username already taken")

        # Create user
        user_id = str(uuid.uuid4())
        hashed_password = self.hash_password(password)
        now = datetime.utcnow()

        await sqlite_manager.execute(
            """
            INSERT INTO users (id, email, username, display_name, hashed_password, is_active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (user_id, email, username, display_name, hashed_password, now, now)
        )

        return {
            "id": user_id,
            "email": email,
            "username": username,
            "display_name": display_name,
            "is_active": True,
            "created_at": now,
        }

    async def authenticate_user(self, email: str, password: str) -> Optional[Dict[str, Any]]:
        """Authenticate a user with email and password"""
        user = await sqlite_manager.fetchone(
            "SELECT * FROM users WHERE email = ? AND is_active = 1",
            (email,)
        )

        if not user:
            return None

        if not self.verify_password(password, user["hashed_password"]):
            return None

        return user

    async def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get a user by ID"""
        return await sqlite_manager.fetchone(
            "SELECT id, email, username, display_name, is_active, created_at, updated_at FROM users WHERE id = ?",
            (user_id,)
        )

    async def store_refresh_token(self, user_id: str, token: str) -> str:
        """Store a refresh token in the database"""
        token_id = str(uuid.uuid4())
        token_hash = self.hash_password(token)  # Hash the token for storage
        expires_at = datetime.utcnow() + timedelta(days=self.refresh_token_expire_days)

        await sqlite_manager.execute(
            """
            INSERT INTO refresh_tokens (id, user_id, token_hash, expires_at, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (token_id, user_id, token_hash, expires_at, datetime.utcnow())
        )

        return token_id

    async def validate_refresh_token(self, token: str, user_id: str) -> bool:
        """Validate a refresh token"""
        payload = self.decode_token(token)
        if not payload or payload.get("type") != "refresh":
            return False

        # Check if token exists in database and is not expired
        tokens = await sqlite_manager.fetchall(
            """
            SELECT * FROM refresh_tokens
            WHERE user_id = ? AND expires_at > ?
            ORDER BY created_at DESC
            """,
            (user_id, datetime.utcnow())
        )

        for stored_token in tokens:
            if self.verify_password(token, stored_token["token_hash"]):
                return True

        return False

    async def revoke_refresh_token(self, user_id: str, token: str) -> bool:
        """Revoke a refresh token"""
        payload = self.decode_token(token)
        if not payload or payload.get("type") != "refresh":
            return False

        # Find and delete the token
        tokens = await sqlite_manager.fetchall(
            "SELECT * FROM refresh_tokens WHERE user_id = ?",
            (user_id,)
        )

        for stored_token in tokens:
            if self.verify_password(token, stored_token["token_hash"]):
                await sqlite_manager.execute(
                    "DELETE FROM refresh_tokens WHERE id = ?",
                    (stored_token["id"],)
                )
                return True

        return False

    async def revoke_all_refresh_tokens(self, user_id: str) -> int:
        """Revoke all refresh tokens for a user"""
        # execute() returns an async context manager cursor, so we do it directly
        async with sqlite_manager.connection.execute(
            "DELETE FROM refresh_tokens WHERE user_id = ?",
            (user_id,)
        ) as cursor:
            await sqlite_manager.connection.commit()
            return cursor.rowcount

    async def create_password_reset_token(self, email: str) -> Optional[str]:
        """Create a password reset token for a user"""
        user = await sqlite_manager.fetchone(
            "SELECT id FROM users WHERE email = ? AND is_active = 1",
            (email,)
        )

        if not user:
            # Don't reveal if email exists or not
            return None

        # Create reset token
        reset_token = str(uuid.uuid4())
        token_id = str(uuid.uuid4())
        token_hash = self.hash_password(reset_token)
        expires_at = datetime.utcnow() + timedelta(hours=self.reset_token_expire_hours)

        await sqlite_manager.execute(
            """
            INSERT INTO password_reset_tokens (id, user_id, token_hash, expires_at, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (token_id, user["id"], token_hash, expires_at, datetime.utcnow())
        )

        # In production, you would send an email here
        # For now, we'll log the token (for development/testing)
        logger.info(f"Password reset token generated for {email}")

        return reset_token

    async def validate_password_reset_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Validate a password reset token and return the user"""
        # Find valid token
        tokens = await sqlite_manager.fetchall(
            """
            SELECT prt.*, u.id as user_id, u.email
            FROM password_reset_tokens prt
            JOIN users u ON u.id = prt.user_id
            WHERE prt.used = 0 AND prt.expires_at > ?
            """,
            (datetime.utcnow(),)
        )

        for reset_token in tokens:
            if self.verify_password(token, reset_token["token_hash"]):
                return reset_token

        return None

    async def reset_password(self, token: str, new_password: str) -> bool:
        """Reset a user's password using a reset token"""
        token_data = await self.validate_password_reset_token(token)
        if not token_data:
            return False

        user_id = token_data["user_id"]
        hashed_password = self.hash_password(new_password)

        # Update password
        await sqlite_manager.execute(
            """
            UPDATE users
            SET hashed_password = ?, updated_at = ?
            WHERE id = ?
            """,
            (hashed_password, datetime.utcnow(), user_id)
        )

        # Mark token as used
        await sqlite_manager.execute(
            """
            UPDATE password_reset_tokens
            SET used = 1
            WHERE id = ?
            """,
            (token_data["id"],)
        )

        # Revoke all refresh tokens for security
        await self.revoke_all_refresh_tokens(user_id)

        return True


# Global service instance
auth_service = AuthService()
