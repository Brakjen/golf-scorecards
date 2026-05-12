"""Dependency injection factories for the web layer."""

from functools import lru_cache
from importlib.resources import files

from starlette.templating import Jinja2Templates

from golf_scorecards.agents.service import AgentService
from golf_scorecards.auth.repository import UserRepository
from golf_scorecards.auth.service import AuthService
from golf_scorecards.catalog.repository import CourseCatalogRepository
from golf_scorecards.catalog.service import CatalogService
from golf_scorecards.config import get_settings
from golf_scorecards.handicap.repository import SlopeRatingsRepository
from golf_scorecards.handicap.service import HandicapService
from golf_scorecards.insights.service import InsightsService
from golf_scorecards.practice.repository import PracticeRepository
from golf_scorecards.practice.service import PracticeService
from golf_scorecards.rounds.repository import RoundRepository
from golf_scorecards.rounds.service import RoundService
from golf_scorecards.settings_repo import SettingsRepository


def get_templates_directory() -> str:
    """Return the absolute path to the Jinja2 templates directory."""
    return str(files("golf_scorecards").joinpath("templates"))


def get_static_directory() -> str:
    """Return the absolute path to the static assets directory."""
    return str(files("golf_scorecards").joinpath("static"))


@lru_cache(maxsize=1)
def get_catalog_service() -> CatalogService:
    """Return the singleton catalog service."""
    return CatalogService(repository=CourseCatalogRepository())


@lru_cache(maxsize=1)
def get_handicap_service() -> HandicapService:
    """Return the singleton handicap service."""
    return HandicapService(
        repository=SlopeRatingsRepository(catalog_service=get_catalog_service())
    )


@lru_cache(maxsize=1)
def get_templates() -> Jinja2Templates:
    """Return the singleton Jinja2 templates instance."""
    from golf_scorecards.weather.models import WMO_ICONS

    def weather_icon(code: int | None) -> str:
        if code is None:
            return ""
        return WMO_ICONS.get(code, ("❓", "Unknown"))[0]

    def weather_label(code: int | None) -> str:
        if code is None:
            return ""
        return WMO_ICONS.get(code, ("❓", "Unknown"))[1]

    tpl = Jinja2Templates(directory=get_templates_directory())
    tpl.env.globals["weather_icon"] = weather_icon
    tpl.env.globals["weather_label"] = weather_label

    import markdown as _md
    import re as _re
    from markupsafe import Markup

    _RULE_RE = _re.compile(
        r'(?<!/)'           # not preceded by / (avoids matching inside URLs)
        r'(Rules?\s+)'      # "Rule " or "Rules " prefix
        r'(\d+)'            # main rule number
        r'(\.\d+[a-z]?)?'   # optional sub-section like .3b
        r'(\(\d+\))?'       # optional sub-item like (2)
    )

    def _rule_link(m: _re.Match) -> str:
        prefix = m.group(1)          # "Rule " or "Rules "
        rule_num = m.group(2)        # "14"
        sub = m.group(3) or ""       # ".3b" or ""
        sub_item = m.group(4) or ""  # "(2)" or ""
        display = f"{prefix}{rule_num}{sub}{sub_item}"
        base = f"https://www.randa.org/rog/the-rules-of-golf/rule-{rule_num}"
        if sub:
            anchor = f"{rule_num}{sub}".replace(".", "_")
            url = f"{base}#{anchor}"
        else:
            url = base
        return f'<a href="{url}" target="_blank" rel="noopener">{display}</a>'

    def _linkify_rules(html: str) -> str:
        # Skip content already inside <a> tags
        parts = _re.split(r'(<a\s[^>]*>.*?</a>)', html, flags=_re.DOTALL)
        return "".join(
            _RULE_RE.sub(_rule_link, part) if not part.startswith("<a ") else part
            for part in parts
        )

    def md(text: str) -> Markup:
        """Render markdown to HTML with auto-linked rule citations."""
        html = _md.markdown(text, extensions=["fenced_code", "tables"])
        html = _linkify_rules(html)
        return Markup(html)

    tpl.env.filters["md"] = md
    return tpl


@lru_cache(maxsize=1)
def get_round_service() -> RoundService:
    """Return the singleton round service.

    Returns:
        A ``RoundService`` backed by a ``RoundRepository`` configured
        with the database path from application settings.
    """
    settings = get_settings()
    return RoundService(repository=RoundRepository(db_path=settings.db_path))


@lru_cache(maxsize=1)
def get_settings_repo() -> SettingsRepository:
    """Return the singleton settings repository.

    Returns:
        A ``SettingsRepository`` configured with the database path
        from application settings.
    """
    settings = get_settings()
    return SettingsRepository(db_path=settings.db_path)


@lru_cache(maxsize=1)
def get_insights_service() -> InsightsService | None:
    """Return the singleton insights service, or ``None`` if no API key is set.

    Returns:
        An ``InsightsService`` if ``OPENAI_API_KEY`` is configured, else ``None``.
    """
    settings = get_settings()
    if not settings.openai_api_key:
        return None
    return InsightsService(api_key=settings.openai_api_key, db_path=settings.db_path)


@lru_cache(maxsize=1)
def get_agent_service() -> AgentService | None:
    """Return the singleton agent service, or ``None`` if no API key is set."""
    settings = get_settings()
    if not settings.openai_api_key:
        return None
    return AgentService(api_key=settings.openai_api_key, db_path=settings.db_path)


@lru_cache(maxsize=1)
def get_practice_service() -> PracticeService:
    """Return the singleton practice service.

    Returns:
        A ``PracticeService`` backed by a ``PracticeRepository`` configured
        with the database path from application settings.
    """
    settings = get_settings()
    return PracticeService(repository=PracticeRepository(db_path=settings.db_path))


@lru_cache(maxsize=1)
def get_auth_service() -> AuthService:
    """Return the singleton auth service.

    Returns:
        An ``AuthService`` backed by a ``UserRepository`` configured
        with the database path from application settings.
    """
    settings = get_settings()
    return AuthService(
        user_repo=UserRepository(db_path=settings.db_path),
        invite_code=settings.invite_code,
    )
