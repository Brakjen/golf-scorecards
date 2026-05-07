"""Domain models for user authentication."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class User:
    """Represents an authenticated user.

    Attributes:
        id: Hex UUID primary key.
        username: Unique login identifier.
        display_name: Friendly name shown in the UI.
        is_admin: Whether the user has admin privileges.
        created_at: Account creation timestamp.
    """

    id: str
    username: str
    display_name: str
    is_admin: bool
    created_at: datetime
