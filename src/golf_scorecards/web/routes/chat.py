"""Chat routes — multi-turn conversational agents (rules, etc.)."""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from golf_scorecards.agents.registry import AGENTS
from golf_scorecards.agents.service import AgentService
from golf_scorecards.web.dependencies import (
    get_agent_service,
    get_catalog_service,
    get_templates,
)

router = APIRouter(prefix="/chat")
templates = get_templates()


def _require_agent_service(
    agent_service: AgentService | None = Depends(get_agent_service),
) -> AgentService:
    """Dependency that raises 400 if OpenAI is not configured."""
    if agent_service is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OpenAI API key not configured",
        )
    return agent_service


@router.get("", response_class=HTMLResponse)
async def chat_list(
    request: Request,
    agent_service: AgentService | None = Depends(get_agent_service),
) -> HTMLResponse:
    """List all conversations with a sidebar for navigation."""
    user_id = request.state.user.id
    conversations: list[dict] = []
    if agent_service is not None:
        conversations = await agent_service.list_conversations(user_id)

    # Group by agent_key for sidebar
    conversational_agents = {
        k: v for k, v in AGENTS.items() if v.conversational
    }

    return cast(
        HTMLResponse,
        templates.TemplateResponse(
            request=request,
            name="chat.html",
            context={
                "conversations": conversations,
                "agents": conversational_agents,
                "current_conversation": None,
                "enabled": agent_service is not None,
            },
        ),
    )


@router.get("/new", response_class=HTMLResponse)
async def chat_new(
    request: Request,
    agent: str = "rules",
    agent_service: AgentService = Depends(_require_agent_service),
) -> HTMLResponse:
    """Show the new conversation form (with optional course picker for rules)."""
    if agent not in AGENTS or not AGENTS[agent].conversational:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Agent '{agent}' is not a conversational agent",
        )

    catalog = get_catalog_service()
    courses = catalog.list_course_options()

    return cast(
        HTMLResponse,
        templates.TemplateResponse(
            request=request,
            name="chat_new.html",
            context={
                "agent_key": agent,
                "agent_config": AGENTS[agent],
                "courses": courses,
            },
        ),
    )


@router.post("/new")
async def chat_create(
    request: Request,
    agent: str = Form(...),
    course_slug: str = Form(default=""),
    agent_service: AgentService = Depends(_require_agent_service),
) -> RedirectResponse:
    """Create a new conversation and redirect to it."""
    if agent not in AGENTS or not AGENTS[agent].conversational:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Agent '{agent}' is not a conversational agent",
        )

    user_id = request.state.user.id
    conversation_id = await agent_service.create_conversation(
        user_id=user_id,
        agent_key=agent,
        course_slug=course_slug or None,
    )
    return RedirectResponse(url=f"/chat/{conversation_id}", status_code=303)


@router.get("/{conversation_id}", response_class=HTMLResponse)
async def chat_view(
    request: Request,
    conversation_id: str,
    agent_service: AgentService = Depends(_require_agent_service),
) -> HTMLResponse:
    """View a conversation and its messages."""
    user_id = request.state.user.id
    conv = await agent_service.get_conversation(conversation_id, user_id)
    if conv is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    conversations = await agent_service.list_conversations(user_id)

    return cast(
        HTMLResponse,
        templates.TemplateResponse(
            request=request,
            name="chat.html",
            context={
                "conversations": conversations,
                "agents": {k: v for k, v in AGENTS.items() if v.conversational},
                "current_conversation": conv,
                "enabled": True,
            },
        ),
    )


@router.post("/{conversation_id}/message", response_class=HTMLResponse)
async def chat_send_message(
    request: Request,
    conversation_id: str,
    message: str = Form(...),
    agent_service: AgentService = Depends(_require_agent_service),
) -> HTMLResponse:
    """Send a message and return the assistant's response as an HTML fragment."""
    user_id = request.state.user.id
    message_clean = message.strip()
    if not message_clean:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message cannot be empty",
        )

    try:
        assistant_msg = await agent_service.send_message(
            conversation_id, user_id, message_clean,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    # Fetch updated title (may have been auto-generated)
    conv = await agent_service.get_conversation(conversation_id, user_id)
    title = conv["title"] if conv else None

    # Return both the user and assistant message bubbles as HTML fragment
    return cast(
        HTMLResponse,
        templates.TemplateResponse(
            request=request,
            name="chat_message_pair.html",
            context={
                "user_message": message_clean,
                "assistant_message": assistant_msg["content"],
                "updated_title": title,
            },
        ),
    )


@router.post("/{conversation_id}/delete")
async def chat_delete(
    request: Request,
    conversation_id: str,
    agent_service: AgentService = Depends(_require_agent_service),
) -> RedirectResponse:
    """Delete a conversation and redirect to chat list."""
    user_id = request.state.user.id
    await agent_service.delete_conversation(conversation_id, user_id)
    return RedirectResponse(url="/chat", status_code=303)
