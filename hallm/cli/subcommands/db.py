"""Database subcommands."""

import asyncio

import asyncpg
import typer

from hallm.cli.base.shell import fail
from hallm.cli.base.template import render as _render
from hallm.core.settings import settings

app = typer.Typer(help="Database operations.")

_BOOTSTRAP_PATH = settings.CLI_PATH / "subcommands" / "bootstrap"


async def _run_bootstrap() -> None:
    sql_files = sorted(_BOOTSTRAP_PATH.glob("*.sql"))
    if not sql_files:
        typer.echo("No SQL files found in bootstrap directory.")
        return

    typer.echo("==> Connecting to postgres...")
    try:
        conn = await asyncpg.connect(
            dsn=settings.database_url,
        )
    except OSError as exc:
        fail(f"Cannot reach database at postgres: {exc}")
        return
    except asyncpg.PostgresError as exc:
        fail(f"Database connection failed: {exc}")
        return

    try:
        for sql_file in sql_files:
            typer.echo(f"==> Running {sql_file.name}...")
            try:
                sql = _render(
                    sql_file.read_text(),
                    {
                        "POSTGRES_PASSWORD": settings.database["password"],
                    },
                )
            except ValueError as exc:
                fail(str(exc))
                return
            await conn.execute(sql)
    finally:
        await conn.close()

    typer.echo("\nBootstrap complete.")


@app.command()
def bootstrap() -> None:
    """Bootstrap the database (create schemas, roles, and initial grants)."""
    asyncio.run(_run_bootstrap())
