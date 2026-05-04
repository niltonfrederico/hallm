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
    existing = {row["datname"] for row in await conn.fetch("SELECT datname FROM pg_database")}
    dsn_base = settings.database_url.rsplit("/", 1)[0]
    for db_name in _SERVICE_DATABASES:
        if db_name in existing:
            typer.echo(f"  - {db_name}: already exists, ensuring grants")
        else:
            typer.echo(f"  - {db_name}: creating")
            # CREATE DATABASE cannot run in a transaction — asyncpg's execute() is fine here.
            await conn.execute(f'CREATE DATABASE "{db_name}"')

        # Database-level CREATE lets the role install trusted extensions (e.g. pg_trgm).
        await conn.execute(f'GRANT CREATE ON DATABASE "{db_name}" TO "{db_name}"')

        # Schema-level grants let the role create tables / sequences in public.
        svc_conn = await asyncpg.connect(dsn=f"{dsn_base}/{db_name}")
        try:
            await svc_conn.execute(f'GRANT ALL ON SCHEMA public TO "{db_name}"')
            await svc_conn.execute(f'ALTER SCHEMA public OWNER TO "{db_name}"')
        finally:
            await svc_conn.close()


async def _run_bootstrap() -> None:
    sql_files = sorted(_BOOTSTRAP_PATH.glob("*.sql"))
    if not sql_files:
        typer.echo("No SQL files found in bootstrap directory.")
        return

    typer.echo(f"==> Connecting to postgres {settings.database_url}...")
    conn: asyncpg.Connection | None = None
    for attempt in range(20):
        try:
            conn = await asyncpg.connect(dsn=settings.database_url)
            break
        except OSError:
            if attempt == 0:
                typer.echo("  Postgres not ready yet, retrying...")
            await asyncio.sleep(3)
        except asyncpg.PostgresError as exc:
            fail(f"Database connection failed: {exc}")
    if conn is None:
        fail("Cannot reach database at postgres after 60s — is the pod ready?")

    try:
        for sql_file in sql_files:
            typer.echo(f"==> Running {sql_file.name}...")
            try:
                sql = _render(
                    sql_file.read_text(),
                    {
                        "POSTGRES_PASSWORD": settings.database["password"],
                        "PAPERLESS_DB_PASSWORD": settings.paperless_db_password,
                        "GLITCHTIP_DB_PASSWORD": settings.glitchtip_db_password,
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
