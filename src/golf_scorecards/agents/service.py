"""Unified agent service for all LLM interactions.

Handles both one-shot generation (insights, Q&A) and multi-turn
conversations (rules agent). Logs token usage for observability.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import UTC, datetime
from importlib.resources import files

from openai import AsyncOpenAI

from golf_scorecards.agents.registry import AgentConfig, get_agent
from golf_scorecards.db.connection import get_connection

logger = logging.getLogger(__name__)

# Type alias for chat messages
ChatMessage = dict[str, str]


def _load_prompt(prompt_file: str) -> str:
    """Load a system prompt from the ``agents/prompts/`` package directory."""
    return (
        files("golf_scorecards.agents")
        .joinpath(f"prompts/{prompt_file}")
        .read_text(encoding="utf-8")
    )


def _load_context_file(filename: str) -> str:
    """Load a context file from ``agents/rules_data/``."""
    return (
        files("golf_scorecards.agents")
        .joinpath(f"rules_data/{filename}")
        .read_text(encoding="utf-8")
    )


def _load_local_rules(course_slug: str) -> str | None:
    """Load local rules for a specific course, if available."""
    path = files("golf_scorecards.agents").joinpath(
        f"rules_data/local_rules/{course_slug}.md"
    )
    try:
        text = path.read_text(encoding="utf-8")
        # Skip placeholder files
        if "Placeholder" in text and "not yet added" in text:
            return None
        return text
    except FileNotFoundError:
        return None


def _build_system_prompt(
    config: AgentConfig,
    *,
    course_slug: str | None = None,
) -> str:
    """Assemble the full system prompt from the prompt file and context files."""
    prompt = _load_prompt(config.prompt_file)

    for ctx_file in config.context_files:
        content = _load_context_file(ctx_file)
        prompt += f"\n\n---\n\n{content}"

    if course_slug:
        local_rules = _load_local_rules(course_slug)
        if local_rules:
            prompt += f"\n\n---\n\n## Local Rules for this course\n\n{local_rules}"

    return prompt


class AgentService:
    """Unified service for all LLM agent interactions.

    Provides both one-shot calls (for insights/Q&A) and multi-turn
    conversational calls (for the rules agent).

    Args:
        api_key: OpenAI API key.
        db_path: Path to the SQLite database.
    """

    def __init__(self, api_key: str, db_path: str) -> None:
        self._client = AsyncOpenAI(api_key=api_key)
        self._db_path = db_path

    # ── Core LLM call ────────────────────────────────────

    async def _chat_completion(
        self,
        config: AgentConfig,
        messages: list[ChatMessage],
    ) -> tuple[str, int, int]:
        """Make a chat completion call and return (content, prompt_tokens, completion_tokens)."""
        start = time.monotonic()
        response = await self._client.chat.completions.create(
            model=config.model,
            messages=messages,  # type: ignore[arg-type]
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            user=config.key,
        )
        latency_ms = int((time.monotonic() - start) * 1000)

        content = response.choices[0].message.content or ""
        usage = response.usage
        prompt_tokens = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0

        # Check for cached prompt tokens
        cached = 0
        if usage and hasattr(usage, "prompt_tokens_details"):
            details = usage.prompt_tokens_details
            if details and hasattr(details, "cached_tokens"):
                cached = details.cached_tokens or 0

        # Log usage
        await self._log_usage(
            agent_key=config.key,
            model=config.model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
            cached=cached,
        )

        logger.info(
            "Agent %s: %d prompt + %d completion tokens (%d cached) in %dms",
            config.key,
            prompt_tokens,
            completion_tokens,
            cached,
            latency_ms,
        )

        return content, prompt_tokens, completion_tokens

    # ── One-shot API ─────────────────────────────────────

    async def call_oneshot(
        self,
        agent_key: str,
        user_content: str,
        *,
        system_override: str | None = None,
    ) -> str:
        """Make a one-shot LLM call (no conversation history).

        Args:
            agent_key: Registered agent key (e.g. ``"round_insights"``).
            user_content: The user message content.
            system_override: Optional override for the system prompt
                (used by InsightsService which builds its own prompts).

        Returns:
            The assistant's response text.
        """
        config = get_agent(agent_key)
        system_prompt = system_override or _build_system_prompt(config)
        messages: list[ChatMessage] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]
        content, _, _ = await self._chat_completion(config, messages)
        return content

    # ── Conversational API ───────────────────────────────

    async def create_conversation(
        self,
        user_id: str,
        agent_key: str,
        *,
        title: str | None = None,
        course_slug: str | None = None,
    ) -> str:
        """Create a new conversation and return its ID.

        Args:
            user_id: The authenticated user's ID.
            agent_key: Which agent this conversation uses.
            title: Optional title; auto-generated from first message if omitted.
            course_slug: Optional course context for rules agent.

        Returns:
            The new conversation ID.
        """
        conversation_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        context_json = json.dumps({"course_slug": course_slug}) if course_slug else None

        conn = await get_connection(self._db_path)
        try:
            await conn.execute(
                """INSERT INTO conversations (id, user_id, agent_key, title, context_json, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (conversation_id, user_id, agent_key, title, context_json, now, now),
            )
            await conn.commit()
        finally:
            await conn.close()

        return conversation_id

    async def list_conversations(
        self,
        user_id: str,
        agent_key: str | None = None,
    ) -> list[dict]:
        """List conversations for a user, optionally filtered by agent.

        Returns dicts with: id, agent_key, title, context_json, updated_at, message_count.
        """
        conn = await get_connection(self._db_path)
        try:
            query = """
                SELECT c.id, c.agent_key, c.title, c.context_json, c.updated_at,
                       COUNT(m.id) AS message_count
                FROM conversations c
                LEFT JOIN conversation_messages m ON m.conversation_id = c.id
                WHERE c.user_id = ?
            """
            params: list[str] = [user_id]
            if agent_key:
                query += " AND c.agent_key = ?"
                params.append(agent_key)
            query += " GROUP BY c.id ORDER BY c.updated_at DESC"

            rows = await conn.execute_fetchall(query, params)
            return [dict(r) for r in rows]
        finally:
            await conn.close()

    async def get_conversation(self, conversation_id: str, user_id: str) -> dict | None:
        """Get a single conversation with its messages."""
        conn = await get_connection(self._db_path)
        try:
            rows = await conn.execute_fetchall(
                "SELECT * FROM conversations WHERE id = ? AND user_id = ?",
                (conversation_id, user_id),
            )
            if not rows:
                return None
            conv = dict(rows[0])

            msg_rows = await conn.execute_fetchall(
                """SELECT id, role, content, tokens_used, created_at
                   FROM conversation_messages
                   WHERE conversation_id = ?
                   ORDER BY created_at ASC""",
                (conversation_id,),
            )
            conv["messages"] = [dict(r) for r in msg_rows]
            return conv
        finally:
            await conn.close()

    async def delete_conversation(self, conversation_id: str, user_id: str) -> bool:
        """Delete a conversation and all its messages. Returns True if deleted."""
        conn = await get_connection(self._db_path)
        try:
            cursor = await conn.execute(
                "DELETE FROM conversations WHERE id = ? AND user_id = ?",
                (conversation_id, user_id),
            )
            await conn.commit()
            return cursor.rowcount > 0
        finally:
            await conn.close()

    async def send_message(
        self,
        conversation_id: str,
        user_id: str,
        user_content: str,
    ) -> dict:
        """Send a user message and get the assistant's response.

        Loads the full conversation history, appends the new message,
        calls the LLM, saves both messages, and returns the assistant message.

        Returns:
            Dict with: id, role, content, tokens_used, created_at.
        """
        conv = await self.get_conversation(conversation_id, user_id)
        if conv is None:
            msg = f"Conversation {conversation_id} not found"
            raise ValueError(msg)

        config = get_agent(conv["agent_key"])
        context = json.loads(conv["context_json"]) if conv["context_json"] else {}
        course_slug = context.get("course_slug")

        # Build messages for LLM
        system_prompt = _build_system_prompt(config, course_slug=course_slug)
        messages: list[ChatMessage] = [
            {"role": "system", "content": system_prompt},
        ]

        # Add conversation history
        for msg_row in conv["messages"]:
            messages.append({
                "role": msg_row["role"],
                "content": msg_row["content"],
            })

        # Add new user message
        messages.append({"role": "user", "content": user_content})

        # Call LLM
        response_content, prompt_tokens, completion_tokens = await self._chat_completion(
            config, messages,
        )
        total_tokens = prompt_tokens + completion_tokens

        # Save both messages
        now = datetime.now(UTC).isoformat()
        user_msg_id = str(uuid.uuid4())
        assistant_msg_id = str(uuid.uuid4())

        conn = await get_connection(self._db_path)
        try:
            await conn.execute(
                """INSERT INTO conversation_messages (id, conversation_id, role, content, tokens_used, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (user_msg_id, conversation_id, "user", user_content, None, now),
            )
            await conn.execute(
                """INSERT INTO conversation_messages (id, conversation_id, role, content, tokens_used, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (assistant_msg_id, conversation_id, "assistant", response_content, total_tokens, now),
            )

            # Auto-generate title from first exchange if not set
            if conv["title"] is None:
                title = await self._generate_title(user_content, response_content)
                await conn.execute(
                    "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
                    (title, now, conversation_id),
                )
            else:
                await conn.execute(
                    "UPDATE conversations SET updated_at = ? WHERE id = ?",
                    (now, conversation_id),
                )

            await conn.commit()
        finally:
            await conn.close()

        return {
            "id": assistant_msg_id,
            "role": "assistant",
            "content": response_content,
            "tokens_used": total_tokens,
            "created_at": now,
        }

    # ── Title generation ─────────────────────────────────

    async def _generate_title(self, question: str, answer: str) -> str:
        """Generate a short conversation title from the first Q&A exchange."""
        try:
            response = await self._client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Generate a short title (max 6 words) summarising this golf rules Q&A. "
                            "No quotes, no punctuation at the end. Just the title."
                        ),
                    },
                    {"role": "user", "content": f"Q: {question[:200]}\nA: {answer[:300]}"},
                ],
                temperature=0.2,
                max_tokens=30,
            )
            title = (response.choices[0].message.content or "").strip().strip('"\'')
            return title[:80] if title else question[:80]
        except Exception:
            logger.warning("Title generation failed, falling back to truncation")
            return question[:80]

    # ── Usage logging ────────────────────────────────────

    async def _log_usage(
        self,
        *,
        agent_key: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        latency_ms: int,
        cached: int = 0,
    ) -> None:
        """Write a row to the agent usage log."""
        conn = await get_connection(self._db_path)
        try:
            await conn.execute(
                """INSERT INTO agent_usage_log
                   (agent_key, model, prompt_tokens, completion_tokens, latency_ms, cached, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    agent_key,
                    model,
                    prompt_tokens,
                    completion_tokens,
                    latency_ms,
                    cached,
                    datetime.now(UTC).isoformat(),
                ),
            )
            await conn.commit()
        finally:
            await conn.close()
