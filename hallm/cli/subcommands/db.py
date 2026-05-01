"""Database subcommands."""

import asyncio

import asyncpg
import typer

from hallm.cli.base.shell import fail
from hallm.cli.base.template import render as _render
from hallm.core.settings import settings

app = typer.Typer(help="Database operations.", no_args_is_help=True)

_BOOTSTRAP_PATH = settings.CLI_PATH / "subcommands" / "bootstrap"

# Per-service databases co-hosted on the shared postgres pod.
_SERVICE_DATABASES: tuple[str, ...] = ("glitchtip", "paperless")


async def _ensure_service_databases(conn: asyncpg.Connection) -> None:
    owner = settings.database["user"]
    existing = {row["datname"] for row in await conn.fetch("SELECT datname FROM pg_database")}
    for db_name in _SERVICE_DATABASES:
        if db_name in existing:
            typer.echo(f"  - {db_name}: already exists")
            continue
        typer.echo(f"  - {db_name}: creating")
        # CREATE DATABASE cannot run in a transaction — asyncpg's execute() is fine here.
        await conn.execute(f'CREATE DATABASE "{db_name}" OWNER "{owner}"')


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
    except asyncpg.PostgresError as exc:
        fail(f"Database connection failed: {exc}")

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
            await conn.execute(sql)

        typer.echo("==> Ensuring per-service databases...")
        await _ensure_service_databases(conn)
    finally:
        await conn.close()

    typer.echo("\nBootstrap complete.")


@app.command()
def bootstrap() -> None:
    """Bootstrap the database (create schemas, roles, and initial grants)."""
    asyncio.run(_run_bootstrap())
