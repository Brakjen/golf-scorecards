"""OpenAI chat completion integration and insights caching."""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import UTC, datetime

from openai import AsyncOpenAI

from golf_scorecards.db.connection import get_connection
from golf_scorecards.insights.prompts import SYSTEM_PROMPT, build_user_message
from golf_scorecards.insights.serializers import serialize_rounds
from golf_scorecards.rounds.models import Round
from golf_scorecards.rounds.stats import compute_quick_stats

logger = logging.getLogger(__name__)


class InsightsService:
    """Generate and cache LLM coaching insights.

    Uses OpenAI chat completions (GPT-4o) to produce 5 coaching insights
    from the golfer's recent round data. Results are cached in
    ``insights_cache`` keyed by a hash of the round IDs, so repeated
    page loads don't trigger API calls.

    Args:
        api_key: OpenAI API key.
        db_path: Filesystem path to the SQLite database file.
        model: OpenAI model to use for completions.
    """

    def __init__(
        self,
        api_key: str,
        db_path: str,
        model: str = "gpt-4o",
    ) -> None:
        self._client = AsyncOpenAI(api_key=api_key)
        self._db_path = db_path
        self._model = model

    # ── Public API ───────────────────────────────────────

    async def get_cached_insights(self) -> list[str] | None:
        """Read the most recent cached insights.

        Returns:
            A list of insight strings, or ``None`` if no cache exists.
        """
        conn = await get_connection(self._db_path)
        try:
            row = await conn.execute_fetchall(
                "SELECT insights_json FROM insights_cache ORDER BY generated_at DESC LIMIT 1"
            )
            if not row:
                return None
            return json.loads(row[0]["insights_json"])
        finally:
            await conn.close()

    async def generate_insights(
        self,
        rounds: list[Round],
        handicap_index: str | None = None,
    ) -> list[str]:
        """Generate fresh coaching insights from recent rounds.

        Checks the cache first — if the rounds haven't changed since the
        last generation, returns the cached result. Otherwise calls the
        OpenAI API and caches the new insights.

        Args:
            rounds: Recent rounds with full hole data, newest first.
            handicap_index: The player's current WHS handicap index.

        Returns:
            A list of 5 coaching insight strings.

        Raises:
            ValueError: If the API response cannot be parsed as a JSON array.
        """
        if not rounds:
            return []

        rounds_hash = self._hash_rounds(rounds)

        # Check cache
        cached = await self._read_cache(rounds_hash)
        if cached is not None:
            return cached

        # Build prompt
        stats = compute_quick_stats(rounds)
        round_data = serialize_rounds(rounds, stats, handicap_index)
        user_message = build_user_message(round_data)

        # Call OpenAI
        insights = await self._call_openai(user_message)

        # Cache result
        await self._write_cache(rounds_hash, insights)

        return insights

    # ── Private helpers ──────────────────────────────────

    async def _call_openai(self, user_message: str) -> list[str]:
        """Make the chat completion API call and parse the response.

        Args:
            user_message: The formatted user message with round data.

        Returns:
            A list of insight strings parsed from the LLM response.

        Raises:
            ValueError: If the response is not a valid JSON array of strings.
        """
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0.7,
            max_tokens=1024,
        )
        content = response.choices[0].message.content or ""
        return self._parse_response(content)

    @staticmethod
    def _parse_response(content: str) -> list[str]:
        """Parse the LLM response as a JSON array of strings.

        Handles responses that may be wrapped in markdown code fences.

        Args:
            content: Raw response text from the LLM.

        Returns:
            A list of insight strings.

        Raises:
            ValueError: If the content cannot be parsed as a JSON array
                of strings.
        """
        text = content.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first and last fence lines
            lines = [line for line in lines if not line.strip().startswith("```")]
            text = "\n".join(lines).strip()

        parsed = json.loads(text)
        if not isinstance(parsed, list) or not all(isinstance(s, str) for s in parsed):
            msg = "Expected a JSON array of strings"
            raise ValueError(msg)
        return parsed

    @staticmethod
    def _hash_rounds(rounds: list[Round]) -> str:
        """Compute a deterministic hash of round IDs and update timestamps.

        Args:
            rounds: Rounds to hash.

        Returns:
            A hex SHA-256 digest.
        """
        data = "|".join(
            f"{r.id}:{r.updated_at.isoformat()}" for r in sorted(rounds, key=lambda r: r.id)
        )
        return hashlib.sha256(data.encode()).hexdigest()

    async def _read_cache(self, rounds_hash: str) -> list[str] | None:
        """Read cached insights matching the given rounds hash.

        Args:
            rounds_hash: SHA-256 hash of the round IDs.

        Returns:
            Cached insights, or ``None`` if no matching cache entry.
        """
        conn = await get_connection(self._db_path)
        try:
            row = await conn.execute_fetchall(
                "SELECT insights_json FROM insights_cache WHERE rounds_hash = ?",
                (rounds_hash,),
            )
            if not row:
                return None
            return json.loads(row[0]["insights_json"])
        finally:
            await conn.close()

    async def _write_cache(self, rounds_hash: str, insights: list[str]) -> None:
        """Write insights to the cache table.

        Replaces any existing cache entries to keep only the latest.

        Args:
            rounds_hash: SHA-256 hash of the round IDs.
            insights: The insight strings to cache.
        """
        conn = await get_connection(self._db_path)
        try:
            await conn.execute("DELETE FROM insights_cache")
            await conn.execute(
                "INSERT INTO insights_cache"
                " (id, generated_at, rounds_hash, insights_json)"
                " VALUES (?, ?, ?, ?)",
                (
                    uuid.uuid4().hex,
                    datetime.now(UTC).isoformat(),
                    rounds_hash,
                    json.dumps(insights),
                ),
            )
            await conn.commit()
        finally:
            await conn.close()
