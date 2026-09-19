import asyncio

import typer
from pydantic import ValidationError
from pydantic_settings import SettingsError

from sys_eden.config import load_settings
from sys_eden.core import Core
from sys_eden.logging import configure_logging

app = typer.Typer(
    name="eden",
    help="Sys Eden - local Windows system intelligence and maintenance.",
)


@app.callback()
def main() -> None:
    """Sys Eden command-line interface."""


@app.command()
def health() -> None:
    """Check whether the Sys Eden core is running correctly."""
    logger = configure_logging()
    try:
        settings = load_settings()
    except (ValidationError, SettingsError):
        typer.echo('{"core":"unavailable","configuration":"error"}')
        raise typer.Exit(1) from None
    summary = asyncio.run(Core(settings).health())
    logger.info("Health check completed", extra={"event_type": "core.health_checked"})
    typer.echo(summary.model_dump_json(indent=2))
    if summary.core != "ok":
        raise typer.Exit(1)
