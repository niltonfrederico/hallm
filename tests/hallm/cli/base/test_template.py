"""Unit tests for hallm.cli.base.template."""

import pytest

from hallm.cli.base.template import render


class TestRender:
    def test_substitutes_known_key(self) -> None:
        result = render("PASSWORD '##POSTGRES_PASSWORD##'", {"POSTGRES_PASSWORD": "s3cr3t"})
        assert result == "PASSWORD 's3cr3t'"

    def test_substitutes_multiple_keys(self) -> None:
        result = render(
            "##POSTGRES_USER## / ##POSTGRES_PASSWORD##",
            {"POSTGRES_USER": "hallm", "POSTGRES_PASSWORD": "s3cr3t"},
        )
        assert result == "hallm / s3cr3t"

    def test_substitutes_repeated_key(self) -> None:
        result = render("##POSTGRES_USER## and ##POSTGRES_USER## again", {"POSTGRES_USER": "hallm"})
        assert result == "hallm and hallm again"

    def test_raises_on_unknown_key(self) -> None:
        with pytest.raises(ValueError, match="##UNKNOWN##"):
            render("##UNKNOWN##", {})

    def test_raises_on_multiple_unknown_keys(self) -> None:
        with pytest.raises(ValueError, match="##A##"):
            render("##A## ##B##", {})

    def test_no_placeholders_returned_unchanged(self) -> None:
        text = "SELECT 1;"
        assert render(text, {}) == text

    def test_partial_match_not_substituted(self) -> None:
        text = "#POSTGRES_PASSWORD#"
        assert render(text, {"POSTGRES_PASSWORD": "s3cr3t"}) == text
