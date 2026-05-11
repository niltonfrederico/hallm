"""Postgres deployment + db bootstrap (roles, databases, grants) post-install."""

from pathlib import Path
from typing import ClassVar

import typer

from hallm.cli.subcommands import db as _db
from hallm.cli.subcommands.cluster.setup_builders.base import App
from hallm.cli.subcommands.cluster.setup_builders.base import Step
from hallm.cli.subcommands.cluster.setup_builders.base import WaitCondition


class PostgresApp(App):
    name: ClassVar[str] = "postgres"
    manifest_path: ClassVar[Path | None] = Path("postgres.yaml")
    wait_target: ClassVar[str | None] = "deploy/postgres"
    wait_condition: ClassVar[WaitCondition] = WaitCondition.AVAILABLE
    wait_timeout: ClassVar[int] = 180


class PostgresStep(Step):
    name: ClassVar[str] = "Setting up postgres"
    app: App = PostgresApp()
    needs_secrets: ClassVar[bool] = True

    def post(self) -> None:
        typer.echo("  Running database bootstrap...")
        _db._run_bootstrap()
