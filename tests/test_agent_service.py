"""Tests for the agent registry, service, and conversations."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from golf_scorecards.agents.registry import AGENTS, AgentConfig, get_agent
from golf_scorecards.agents.service import (
    AgentService,
    _build_system_prompt,
    _load_local_rules,
    _load_prompt,
)
from golf_scorecards.db.connection import init_db_sync


# ── Registry tests ───────────────────────────────────────


class TestRegistry:
    def test_rules_agent_registered(self) -> None:
        config = get_agent("rules")
        assert config.key == "rules"
        assert config.conversational is True
        assert config.model == "gpt-4.1"
        assert config.temperature == 0.1

    def test_round_insights_registered(self) -> None:
        config = get_agent("round_insights")
        assert config.key == "round_insights"
        assert config.conversational is False

    def test_qa_registered(self) -> None:
        config = get_agent("qa")
        assert config.key == "qa"
        assert config.conversational is False

    def test_unknown_agent_raises(self) -> None:
        with pytest.raises(KeyError):
            get_agent("nonexistent")

    def test_all_agents_have_prompt_files(self) -> None:
        for key, config in AGENTS.items():
            # Should not raise
            text = _load_prompt(config.prompt_file)
            assert len(text) > 10, f"Prompt for {key} is too short"


# ── Prompt loading tests ─────────────────────────────────


class TestPromptLoading:
    def test_load_rules_prompt(self) -> None:
        text = _load_prompt("rules.md")
        assert "Rules of Golf" in text

    def test_load_round_insights_prompt(self) -> None:
        text = _load_prompt("round_insights.md")
        assert "coaching insights" in text.lower()

    def test_load_qa_prompt(self) -> None:
        text = _load_prompt("qa.md")
        assert "question" in text.lower()

    def test_build_system_prompt_with_context_files(self) -> None:
        config = get_agent("rules")
        prompt = _build_system_prompt(config)
        # Should contain rules prompt AND the rules of golf text
        assert "Rules of Golf" in prompt
        assert "Rule 1" in prompt

    def test_build_system_prompt_without_context(self) -> None:
        config = get_agent("round_insights")
        prompt = _build_system_prompt(config)
        assert "coaching insights" in prompt.lower()

    def test_local_rules_loads_real_content(self) -> None:
        result = _load_local_rules("sola-golfklubb-forus")
        assert result is not None
        assert len(result) > 100

    def test_local_rules_missing_returns_none(self) -> None:
        result = _load_local_rules("nonexistent-course")
        assert result is None


# ── Service tests ────────────────────────────────────────


@pytest.fixture()
def db_path(tmp_path: Path) -> str:
    """Create a temporary DB with all tables and a test user."""
    path = str(tmp_path / "test.db")
    init_db_sync(path)
    # Insert test users for FK constraints
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(
        "INSERT INTO users (id, username, password_hash, display_name, created_at) "
        "VALUES ('user1', 'testuser1', 'hash', 'Test User 1', '2024-01-01T00:00:00')"
    )
    conn.execute(
        "INSERT INTO users (id, username, password_hash, display_name, created_at) "
        "VALUES ('user2', 'testuser2', 'hash', 'Test User 2', '2024-01-01T00:00:00')"
    )
    conn.commit()
    conn.close()
    return path


@pytest.fixture()
def agent_service(db_path: str) -> AgentService:
    return AgentService(api_key="test-key", db_path=db_path)


class TestConversations:
    @pytest.mark.asyncio()
    async def test_create_conversation(self, agent_service: AgentService, db_path: str) -> None:
        conv_id = await agent_service.create_conversation(
            user_id="user1",
            agent_key="rules",
        )
        assert conv_id is not None
        assert len(conv_id) == 36  # UUID format

    @pytest.mark.asyncio()
    async def test_list_conversations(self, agent_service: AgentService) -> None:
        await agent_service.create_conversation(user_id="user1", agent_key="rules")
        await agent_service.create_conversation(user_id="user1", agent_key="rules")

        convs = await agent_service.list_conversations("user1")
        assert len(convs) == 2

    @pytest.mark.asyncio()
    async def test_list_conversations_filters_by_agent(self, agent_service: AgentService) -> None:
        await agent_service.create_conversation(user_id="user1", agent_key="rules")
        # qa is not conversational, but we can still create a conversation for it in tests
        await agent_service.create_conversation(user_id="user1", agent_key="qa")

        rules_convs = await agent_service.list_conversations("user1", agent_key="rules")
        assert len(rules_convs) == 1

    @pytest.mark.asyncio()
    async def test_list_conversations_isolates_users(self, agent_service: AgentService) -> None:
        await agent_service.create_conversation(user_id="user1", agent_key="rules")
        await agent_service.create_conversation(user_id="user2", agent_key="rules")

        assert len(await agent_service.list_conversations("user1")) == 1
        assert len(await agent_service.list_conversations("user2")) == 1

    @pytest.mark.asyncio()
    async def test_get_conversation(self, agent_service: AgentService) -> None:
        conv_id = await agent_service.create_conversation(
            user_id="user1",
            agent_key="rules",
            title="Test convo",
            course_slug="sola-golfklubb-forus",
        )
        conv = await agent_service.get_conversation(conv_id, "user1")
        assert conv is not None
        assert conv["title"] == "Test convo"
        assert conv["agent_key"] == "rules"
        assert conv["messages"] == []
        assert "sola-golfklubb-forus" in conv["context_json"]

    @pytest.mark.asyncio()
    async def test_get_conversation_wrong_user(self, agent_service: AgentService) -> None:
        conv_id = await agent_service.create_conversation(user_id="user1", agent_key="rules")
        conv = await agent_service.get_conversation(conv_id, "user2")
        assert conv is None

    @pytest.mark.asyncio()
    async def test_delete_conversation(self, agent_service: AgentService) -> None:
        conv_id = await agent_service.create_conversation(user_id="user1", agent_key="rules")
        deleted = await agent_service.delete_conversation(conv_id, "user1")
        assert deleted is True

        conv = await agent_service.get_conversation(conv_id, "user1")
        assert conv is None

    @pytest.mark.asyncio()
    async def test_delete_conversation_wrong_user(self, agent_service: AgentService) -> None:
        conv_id = await agent_service.create_conversation(user_id="user1", agent_key="rules")
        deleted = await agent_service.delete_conversation(conv_id, "user2")
        assert deleted is False

    @pytest.mark.asyncio()
    async def test_send_message(self, agent_service: AgentService) -> None:
        conv_id = await agent_service.create_conversation(user_id="user1", agent_key="rules")

        # Mock the OpenAI call
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "A ball in a penalty area can be played as it lies."
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 20
        mock_response.usage.prompt_tokens_details = None

        agent_service._client.chat.completions.create = AsyncMock(return_value=mock_response)

        result = await agent_service.send_message(conv_id, "user1", "What is a penalty area?")

        assert result["role"] == "assistant"
        assert "penalty area" in result["content"]
        assert result["tokens_used"] == 120

        # Verify messages were saved
        conv = await agent_service.get_conversation(conv_id, "user1")
        assert len(conv["messages"]) == 2
        assert conv["messages"][0]["role"] == "user"
        assert conv["messages"][1]["role"] == "assistant"

    @pytest.mark.asyncio()
    async def test_send_message_auto_titles(self, agent_service: AgentService) -> None:
        conv_id = await agent_service.create_conversation(user_id="user1", agent_key="rules")

        # First call: the rules agent response; second call: the title generation
        rules_response = MagicMock()
        rules_response.choices = [MagicMock()]
        rules_response.choices[0].message.content = "Answer."
        rules_response.usage = MagicMock()
        rules_response.usage.prompt_tokens = 10
        rules_response.usage.completion_tokens = 5
        rules_response.usage.prompt_tokens_details = None

        title_response = MagicMock()
        title_response.choices = [MagicMock()]
        title_response.choices[0].message.content = "Out of Bounds Explained"

        agent_service._client.chat.completions.create = AsyncMock(
            side_effect=[rules_response, title_response],
        )

        await agent_service.send_message(conv_id, "user1", "What is out of bounds?")

        conv = await agent_service.get_conversation(conv_id, "user1")
        assert conv["title"] == "Out of Bounds Explained"

    @pytest.mark.asyncio()
    async def test_send_message_nonexistent_conversation(self, agent_service: AgentService) -> None:
        with pytest.raises(ValueError, match="not found"):
            await agent_service.send_message("fake-id", "user1", "Hello")

    @pytest.mark.asyncio()
    async def test_call_oneshot(self, agent_service: AgentService) -> None:
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '["Insight 1", "Insight 2", "Insight 3"]'
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 500
        mock_response.usage.completion_tokens = 100
        mock_response.usage.prompt_tokens_details = None

        agent_service._client.chat.completions.create = AsyncMock(return_value=mock_response)

        result = await agent_service.call_oneshot("round_insights", "Round data here")
        assert "Insight 1" in result


class TestUsageLogging:
    @pytest.mark.asyncio()
    async def test_usage_logged_after_call(self, agent_service: AgentService, db_path: str) -> None:
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Answer."
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 150
        mock_response.usage.completion_tokens = 30
        mock_response.usage.prompt_tokens_details = None

        agent_service._client.chat.completions.create = AsyncMock(return_value=mock_response)

        await agent_service.call_oneshot("qa", "Question here")

        # Check the usage log
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM agent_usage_log").fetchall()
        conn.close()

        assert len(rows) == 1
        assert rows[0]["agent_key"] == "qa"
        assert rows[0]["prompt_tokens"] == 150
        assert rows[0]["completion_tokens"] == 30
