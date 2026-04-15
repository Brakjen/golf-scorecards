"""Dependency injection factories for the web layer."""

from functools import lru_cache
from importlib.resources import files
from pathlib import Path

from starlette.templating import Jinja2Templates

from golf_scorecards.catalog.repository import CourseCatalogRepository
from golf_scorecards.catalog.service import CatalogService
from golf_scorecards.export import ExportService
from golf_scorecards.handicap.repository import SlopeRatingsRepository
from golf_scorecards.handicap.service import HandicapService
from golf_scorecards.scorecards.builder import ScorecardBuilder


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
def get_scorecard_builder() -> ScorecardBuilder:
    """Return the singleton scorecard builder."""
    return ScorecardBuilder()


@lru_cache(maxsize=1)
def get_handicap_service() -> HandicapService:
    """Return the singleton handicap service."""
    return HandicapService(
        repository=SlopeRatingsRepository(catalog_service=get_catalog_service())
    )


@lru_cache(maxsize=1)
def get_templates() -> Jinja2Templates:
    """Return the singleton Jinja2 templates instance."""
    return Jinja2Templates(directory=get_templates_directory())


@lru_cache(maxsize=1)
def get_export_service() -> ExportService:
    """Return the singleton PDF export service."""
    return ExportService(template_dir=Path(get_templates_directory()))
