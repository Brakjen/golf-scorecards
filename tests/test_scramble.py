"""Tests for scramble tag generation and save endpoint logic."""

import json

import pytest

from golf_scorecards.web.routes.play import _scramble_tag, _scramble_tags


class TestScrambleTag:
    def test_first_last(self) -> None:
        assert _scramble_tag("Bjørn Kjelby") == "BjøKje"

    def test_first_only(self) -> None:
        assert _scramble_tag("Erik") == "Eri"

    def test_short_first_name(self) -> None:
        assert _scramble_tag("Bo Li") == "BoLi"

    def test_three_part_name(self) -> None:
        # Uses first word and last word
        assert _scramble_tag("Jan Erik Svensson") == "JanSve"

    def test_empty_string(self) -> None:
        assert _scramble_tag("") == "???"

    def test_whitespace_only(self) -> None:
        assert _scramble_tag("   ") == "???"

    def test_long_names(self) -> None:
        assert _scramble_tag("Alexander Kristiansen") == "AleKri"


class TestScrambleTags:
    def test_parses_json(self) -> None:
        j = json.dumps(["Bjørn Kjelby", "Erik Svensson"])
        tags = _scramble_tags(j)
        assert len(tags) == 2
        assert tags[0] == {"name": "Bjørn Kjelby", "tag": "BjøKje"}
        assert tags[1] == {"name": "Erik Svensson", "tag": "EriSve"}

    def test_none_input(self) -> None:
        assert _scramble_tags(None) == []

    def test_empty_string(self) -> None:
        assert _scramble_tags("") == []

    def test_invalid_json(self) -> None:
        assert _scramble_tags("not json") == []

    def test_filters_empty_names(self) -> None:
        j = json.dumps(["Bjørn Kjelby", "", "  "])
        tags = _scramble_tags(j)
        assert len(tags) == 1
