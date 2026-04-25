"""PDF export from scorecard data using WeasyPrint."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from jinja2 import Environment, FileSystemLoader

if TYPE_CHECKING:
    from golf_scorecards.scorecards.models import PrintableScorecard


class ExportService:
    """Renders a scorecard to PDF bytes."""

    def __init__(self, template_dir: Path) -> None:
        """Initialise with the path to the scorecard templates directory."""
        self._env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=True,
        )

    def _render_html(self, scorecard: PrintableScorecard) -> str:
        """Render the scorecard to an HTML string."""
        template = self._env.get_template("scorecard_print.html")
        return template.render(scorecard=scorecard)

    def to_pdf(self, scorecard: PrintableScorecard) -> bytes:
        """Return PDF bytes for the scorecard at golf-card dimensions.

        Args:
            scorecard: The fully populated scorecard to export.

        Returns:
            Raw PDF bytes.
        """
        html_string = self._render_html(scorecard)
        import weasyprint  # type: ignore[import-untyped]

        doc = weasyprint.HTML(string=html_string)
        return doc.write_pdf()  # type: ignore[no-any-return]
