"""Authentication business logic: register, login, session lookup."""

from __future__ import annotations

import hmac
import uuid
from datetime import UTC, datetime

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from golf_scorecards.auth.models import User
from golf_scorecards.auth.repository import UserRepository

_ph = PasswordHasher()


class AuthService:
    """Orchestrates user registration, login, and session resolution.

    Args:
        user_repo: Repository for user persistence.
        invite_code: Required invite code for registration. Empty string disables the gate.
    """

    def __init__(self, user_repo: UserRepository, invite_code: str) -> None:
        self._repo = user_repo
        self._invite_code = invite_code

    async def register(
        self,
        username: str,
        password: str,
        display_name: str,
        invite_code: str,
    ) -> User | str:
        """Create a new user account.

        Args:
            username: Desired login name (case-insensitive).
            password: Plaintext password (will be hashed with argon2id).
            display_name: Friendly display name.
            invite_code: The invite code provided by the user.

        Returns:
            The created ``User`` on success, or an error message string.
        """
        if self._invite_code and not hmac.compare_digest(invite_code, self._invite_code):
            return "Invalid invite code."

        username_lower = username.strip().lower()
        if not username_lower or len(username_lower) < 2:
            return "Username must be at least 2 characters."
        if len(password) < 6:
            return "Password must be at least 6 characters."

        # Check uniqueness
        existing = await self._repo.get_by_username(username_lower)
        if existing is not None:
            return "Username already taken."

        user_id = uuid.uuid4().hex
        password_hash = _ph.hash(password)
        now = datetime.now(tz=UTC)

        await self._repo.create_user(
            user_id=user_id,
            username=username_lower,
            password_hash=password_hash,
            display_name=display_name.strip() or username_lower,
            created_at=now,
        )

        return User(
            id=user_id,
            username=username_lower,
            display_name=display_name.strip() or username_lower,
            is_admin=False,
            created_at=now,
        )

    async def login(self, username: str, password: str) -> User | None:
        """Verify credentials and return the user on success.

        Args:
            username: Login identifier.
            password: Plaintext password to verify.

        Returns:
            The ``User`` if credentials are valid, otherwise ``None``.
        """
        result = await self._repo.get_by_username(username.strip().lower())
        if result is None:
            # Perform a dummy hash to prevent timing attacks
            _ph.hash("dummy-password-timing-safe")
            return None

        user, password_hash = result
        try:
            _ph.verify(password_hash, password)
        except VerifyMismatchError:
            return None

        return user

    async def get_user_by_id(self, user_id: str) -> User | None:
        """Resolve a user from their stored session ID.

        Args:
            user_id: The hex UUID from the session cookie.

        Returns:
            The ``User`` if found, otherwise ``None``.
        """
        return await self._repo.get_by_id(user_id)

    async def list_users(self) -> list[User]:
        """Return all registered users."""
        return await self._repo.list_users()
