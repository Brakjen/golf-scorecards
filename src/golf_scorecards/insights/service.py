"""OpenAI chat completion integration and insights caching."""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from openai import AsyncOpenAI

from golf_scorecards.db.connection import get_connection
from golf_scorecards.insights.prompts import (
    QA_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    build_qa_user_message,
    build_user_message,
)
from golf_scorecards.insights.serializers import serialize_rounds
from golf_scorecards.rounds.models import Round
from golf_scorecards.rounds.stats import compute_quick_stats

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class QAEntry:
    """A cached question/answer pair.

    Attributes:
        question: The user's free-text question.
        answer: The LLM's plain-prose response.
        generated_at: ISO-8601 timestamp when the answer was produced.
    """

    question: str
    answer: str
    generated_at: str


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

    async def get_cached_insights(
        self, cache_key: str = "dashboard",
    ) -> list[str] | None:
        """Read the most recent cached insights for a cache key.

        Args:
            cache_key: Scope identifier (``"dashboard"`` or
                ``f"round:{round_id}"``).

        Returns:
            A list of insight strings, or ``None`` if no cache exists.
        """
        conn = await get_connection(self._db_path)
        try:
            row = await conn.execute_fetchall(
                "SELECT insights_json FROM insights_cache"
                " WHERE cache_key = ?"
                " ORDER BY generated_at DESC LIMIT 1",
                (cache_key,),
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
        *,
        force: bool = False,
        cache_key: str = "dashboard",
    ) -> list[str]:
        """Generate fresh coaching insights from recent rounds.

        Checks the cache first — if the rounds haven't changed since the
        last generation, returns the cached result. Otherwise calls the
        OpenAI API and caches the new insights.

        Args:
            rounds: Recent rounds with full hole data, newest first.
            handicap_index: The player's current WHS handicap index.
            force: Skip the cache and always call the API.
            cache_key: Scope for cache isolation (``"dashboard"`` or
                ``f"round:{id}"``).

        Returns:
            A list of 3 coaching insight strings.

        Raises:
            ValueError: If the API response cannot be parsed as a JSON array.
        """
        if not rounds:
            return []

        rounds_hash = self._hash_rounds(rounds)

        # Check cache (skip when force-refreshing)
        if not force:
            cached = await self._read_cache(cache_key, rounds_hash)
            if cached is not None:
                return cached

        # Build prompt
        stats = compute_quick_stats(rounds)
        round_data = serialize_rounds(rounds, stats, handicap_index)
        user_message = build_user_message(round_data)

        # Call OpenAI
        insights = await self._call_openai(user_message)

        # Cache result
        await self._write_cache(cache_key, rounds_hash, insights)

        return insights

    async def answer_question(
        self,
        rounds: list[Round],
        question: str,
        handicap_index: str | None = None,
    ) -> QAEntry:
        """Answer a free-text question about the golfer's recent rounds.

        Sends the question along with the same serialized round data
        used by ``generate_insights`` to the LLM and returns a plain-prose
        answer. Answers are not cached — every call hits the API.

        Args:
            rounds: Rounds to use as context, newest first.
            question: The user's free-text question.
            handicap_index: The player's WHS handicap index.

        Returns:
            A ``QAEntry`` with the original question, the answer, and the
            generation timestamp.

        Raises:
            ValueError: If the question is empty or rounds is empty.
        """
        question_clean = question.strip()
        if not question_clean:
            msg = "Question is empty"
            raise ValueError(msg)
        if not rounds:
            msg = "No rounds provided for context"
            raise ValueError(msg)

        stats = compute_quick_stats(rounds)
        round_data = serialize_rounds(rounds, stats, handicap_index)
        user_message = build_qa_user_message(round_data, question_clean)
        answer = await self._call_openai_qa(user_message)

        return QAEntry(
            question=question_clean,
            answer=answer,
            generated_at=datetime.now(UTC).isoformat(),
        )

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

    async def _read_cache(
        self, cache_key: str, rounds_hash: str,
    ) -> list[str] | None:
        """Read cached insights matching the given cache key and rounds hash.

        Args:
            cache_key: Scope identifier.
            rounds_hash: SHA-256 hash of the round IDs.

        Returns:
            Cached insights, or ``None`` if no matching cache entry.
        """
        conn = await get_connection(self._db_path)
        try:
            row = await conn.execute_fetchall(
                "SELECT insights_json FROM insights_cache"
                " WHERE cache_key = ? AND rounds_hash = ?",
                (cache_key, rounds_hash),
            )
            if not row:
                return None
            return json.loads(row[0]["insights_json"])
        finally:
            await conn.close()

    async def _write_cache(
        self, cache_key: str, rounds_hash: str, insights: list[str],
    ) -> None:
        """Write insights to the cache table for a given scope.

        Replaces any existing entry for the same ``cache_key`` so that
        only one cached result per scope is retained.

        Args:
            cache_key: Scope identifier.
            rounds_hash: SHA-256 hash of the round IDs.
            insights: The insight strings to cache.
        """
        conn = await get_connection(self._db_path)
        try:
            await conn.execute(
                "DELETE FROM insights_cache WHERE cache_key = ?", (cache_key,),
            )
            await conn.execute(
                "INSERT INTO insights_cache"
                " (id, cache_key, generated_at, rounds_hash, insights_json)"
                " VALUES (?, ?, ?, ?, ?)",
                (
                    uuid.uuid4().hex,
                    cache_key,
                    datetime.now(UTC).isoformat(),
                    rounds_hash,
                    json.dumps(insights),
                ),
            )
            await conn.commit()
        finally:
            await conn.close()

    # ── Q&A helpers ──────────────────────────────────────

    async def _call_openai_qa(self, user_message: str) -> str:
        """Call the chat API for a free-form Q&A request.

        Args:
            user_message: The formatted user message containing round
                data and the user's question.

        Returns:
            The model's plain-prose answer (whitespace stripped).
        """
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": QA_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0.5,
            max_tokens=1024,
        )
        return (response.choices[0].message.content or "").strip()
