"""Database subcommands."""

import asyncio

import asyncpg
import typer

from hallm.cli.base.shell import fail
from hallm.cli.base.template import render as _render
from hallm.core.settings import settings

app = typer.Typer(help="Database operations.")

_BOOTSTRAP_PATH = settings.CLI_PATH / "subcommands" / "bootstrap"


def _substitutions() -> dict[str, str]:
    return {
        "POSTGRES_PASSWORD": settings.database["password"],
        "POSTGRES_USER": settings.database["user"],
        "POSTGRES_DB": settings.database["name"],
        "POSTGRES_HOST": settings.database["host"],
        "DATABASE_DRIVER": settings.database["driver"],
    }


async def _run_bootstrap() -> None:
    sql_files = sorted(_BOOTSTRAP_PATH.glob("*.sql"))
    if not sql_files:
        typer.echo("No SQL files found in bootstrap directory.")
        return

    subs = _substitutions()

    typer.echo(f"==> Connecting to {settings.database['host']}...")
    try:
        conn = await asyncpg.connect(
            host=settings.database["host"],
            user=settings.database["user"],
            password=settings.database["password"],
            database=settings.database["name"],
        )
    except OSError as exc:
        fail(f"Cannot reach database at {settings.database['host']}: {exc}")
        return
    except asyncpg.PostgresError as exc:
        fail(f"Database connection failed: {exc}")
        return

    async with conn:
        for sql_file in sql_files:
            typer.echo(f"==> Running {sql_file.name}...")
            try:
                sql = _render(sql_file.read_text(), subs)
            except ValueError as exc:
                fail(str(exc))
                return
            await conn.execute(sql)

    typer.echo("\nBootstrap complete.")


@app.command()
def bootstrap() -> None:
    """Bootstrap the database (create schemas, roles, and initial grants)."""
    asyncio.run(_run_bootstrap())
