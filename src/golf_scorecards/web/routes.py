"""FastAPI route handlers for scorecard creation, preview, and export."""

from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, Response

from golf_scorecards.catalog.service import CatalogLookupError, CatalogService
from golf_scorecards.export import ExportService
from golf_scorecards.handicap.service import HandicapLookupError, HandicapService
from golf_scorecards.scorecards.builder import ScorecardBuilder
from golf_scorecards.scorecards.forms import ScorecardFormData, parse_scorecard_form
from golf_scorecards.scorecards.models import PrintableScorecard
from golf_scorecards.web.dependencies import (
    get_catalog_service,
    get_export_service,
    get_handicap_service,
    get_scorecard_builder,
    get_templates,
)

router = APIRouter()
templates = get_templates()


def _build_scorecard(
    form_data: ScorecardFormData,
    catalog_service: CatalogService,
    handicap_service: HandicapService,
    scorecard_builder: ScorecardBuilder,
) -> PrintableScorecard:
    """Shared scorecard construction used by preview and export routes."""
    try:
        course = catalog_service.get_course(form_data.course_slug)
    except CatalogLookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc

    tee = None
    if form_data.tee_name is not None:
        try:
            tee = catalog_service.get_tee(form_data.course_slug, form_data.tee_name)
        except CatalogLookupError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
            ) from exc

    handicap = None
    if form_data.handicap_index is not None and form_data.tee_name is not None:
        profile_key = form_data.handicap_profile or "men"
        if not handicap_service.has_ratings(form_data.course_slug, form_data.tee_name):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"No slope data available for {course.course_name} "
                    f"tee {form_data.tee_name}."
                ),
            )
        try:
            handicap = handicap_service.compute_playing_handicap(
                course_slug=form_data.course_slug,
                tee_name=form_data.tee_name,
                profile_key=profile_key,
                handicap_index=form_data.handicap_index,
            )
        except HandicapLookupError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            ) from exc

    return scorecard_builder.build(
        form_data=form_data,
        course=course,
        tee=tee,
        handicap=handicap,
    )


@router.get("/", response_class=HTMLResponse)
async def home(
    request: Request,
    catalog_service: CatalogService = Depends(get_catalog_service),
) -> HTMLResponse:
    """Render the course-selection and scorecard-creation form."""
    course_options = catalog_service.list_course_options()
    initial_course = course_options[0]
    initial_tee = initial_course["tees"][0]

    return cast(
        HTMLResponse,
        templates.TemplateResponse(
            request=request,
            name="home.html",
            context={
                "course_options": course_options,
                "initial_course_slug": initial_course["course_slug"],
                "initial_tee_name": initial_tee,
            },
        ),
    )


@router.post("/scorecards/preview", response_class=HTMLResponse)
async def scorecard_preview(
    request: Request,
    form_data: ScorecardFormData = Depends(parse_scorecard_form),
    catalog_service: CatalogService = Depends(get_catalog_service),
    handicap_service: HandicapService = Depends(get_handicap_service),
    scorecard_builder: ScorecardBuilder = Depends(get_scorecard_builder),
) -> HTMLResponse:
    """Build and render the scorecard preview page."""
    scorecard = _build_scorecard(
        form_data, catalog_service, handicap_service, scorecard_builder,
    )

    return cast(
        HTMLResponse,
        templates.TemplateResponse(
            request=request,
            name="scorecard_preview.html",
            context={"scorecard": scorecard},
        ),
    )


@router.post("/scorecards/export/pdf")
async def scorecard_export_pdf(
    form_data: ScorecardFormData = Depends(parse_scorecard_form),
    catalog_service: CatalogService = Depends(get_catalog_service),
    handicap_service: HandicapService = Depends(get_handicap_service),
    scorecard_builder: ScorecardBuilder = Depends(get_scorecard_builder),
    export_service: ExportService = Depends(get_export_service),
) -> Response:
    """Generate and return a PDF scorecard as a file download."""
    scorecard = _build_scorecard(
        form_data, catalog_service, handicap_service, scorecard_builder,
    )
    pdf_bytes = export_service.to_pdf(scorecard)
    date_part = scorecard.meta.round_date.isoformat() if scorecard.meta.round_date else "undated"
    tee_part = f"_{scorecard.meta.tee_name}" if scorecard.meta.tee_name else ""
    filename = (
        f"scorecard_{scorecard.meta.course_name}{tee_part}"
        f"_{date_part}.pdf"
    ).replace(" ", "_")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
