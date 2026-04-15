"""Tests for the legacy course data helper functions."""

from golf_scorecards.course_data import load_home_courses


def test_manual_courses_dataset_shape() -> None:
    data = load_home_courses()

    assert data["country_code"] == "NO"
    assert data["dataset"] == "manual-course-catalog"
    assert len(data["courses"]) == 6
    assert {course["course_slug"] for course in data["courses"]} >= {
        "sola-golfklubb-forus",
        "sola-golfklubb-solastranden",
        "stavanger-golfklubb",
        "randaberg-golfklubb-tungenes",
        "kvinnherad-golfklubb",
    }
