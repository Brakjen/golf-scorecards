"""Agent configuration registry.

Each agent has a configuration that controls model selection, temperature,
system prompt, and whether it supports multi-turn conversations.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AgentConfig:
    """Configuration for a single agent.

    Attributes:
        key: Unique identifier (e.g. ``"rules"``, ``"round_insights"``).
        prompt_file: Path to ``.md`` system prompt relative to ``agents/prompts/``.
        model: OpenAI model name.
        temperature: Sampling temperature.
        max_tokens: Maximum response tokens.
        context_files: Extra files appended to the system prompt (relative to
            ``agents/rules_data/``).
        conversational: ``True`` for multi-turn chat agents, ``False`` for
            one-shot generation.
    """

    key: str
    prompt_file: str
    model: str = "gpt-4.1"
    temperature: float = 0.3
    max_tokens: int = 1024
    context_files: list[str] = field(default_factory=list)
    conversational: bool = False


AGENTS: dict[str, AgentConfig] = {
    "round_insights": AgentConfig(
        key="round_insights",
        prompt_file="round_insights.md",
        model="gpt-4o",
        temperature=0.7,
        max_tokens=1024,
        conversational=False,
    ),
    "qa": AgentConfig(
        key="qa",
        prompt_file="qa.md",
        model="gpt-4o",
        temperature=0.5,
        max_tokens=1024,
        conversational=False,
    ),
    "rules": AgentConfig(
        key="rules",
        prompt_file="rules.md",
        model="gpt-4.1",
        temperature=0.1,
        max_tokens=2048,
        context_files=["rules_of_golf.md"],
        conversational=True,
    ),
}


def get_agent(key: str) -> AgentConfig:
    """Look up an agent configuration by key.

    Raises:
        KeyError: If the agent key is not registered.
    """
    return AGENTS[key]
