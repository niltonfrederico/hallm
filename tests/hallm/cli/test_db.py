"""Unit tests for the db CLI subcommand."""

import typer

from hallm.cli.subcommands.db import app


def test_app_is_typer_instance():
    assert isinstance(app, typer.Typer)


def test_no_commands_registered():
    assert app.registered_commands == []
