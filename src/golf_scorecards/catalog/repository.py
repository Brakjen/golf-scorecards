"""Repository for loading course catalog data from packaged JSON."""

import json
from importlib.resources import files
from typing import Any, cast

from golf_scorecards.catalog.models import CourseCatalog


class CourseCatalogRepository:
    """Loads the course catalog from the bundled JSON resource."""
    resource_path = "data/courses/no/manual_courses.json"

    def get_catalog_path(self) -> str:
        """Return the absolute filesystem path to the catalog JSON file."""
        return str(files("golf_scorecards").joinpath(self.resource_path))

    def load_raw_catalog(self) -> dict[str, Any]:
        """Load the catalog JSON as a raw dictionary."""
        course_file = files("golf_scorecards").joinpath(self.resource_path)
        return cast(dict[str, Any], json.loads(course_file.read_text(encoding="utf-8")))

    def load_catalog(self) -> CourseCatalog:
        """Load and validate the catalog into a ``CourseCatalog`` model."""
        return CourseCatalog.model_validate(self.load_raw_catalog())
