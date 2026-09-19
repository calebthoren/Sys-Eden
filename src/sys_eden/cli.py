import asyncio
import json
from typing import Annotated

import typer
from pydantic import ValidationError
from pydantic_settings import SettingsError

from sys_eden.config import load_settings
from sys_eden.core import Core
from sys_eden.inspection import QUERIES, collect
from sys_eden.logging import configure_logging
from sys_eden.windows import WindowsCimReader

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


@app.command()
def inspect(component: Annotated[str, typer.Argument()] = "all") -> None:
    """Read OS, CPU, and RAM information locally as the current user."""
    if component != "all" and component not in QUERIES:
        raise typer.BadParameter("Supported components: all, os, cpu, ram")

    async def run():
        reader = WindowsCimReader()
        return [await collect(name, reader) for name in (
            list(QUERIES) if component == "all" else [component]
        )]

    results = asyncio.run(run())
    typer.echo(json.dumps([result.model_dump(mode="json") for result in results], indent=2))
    if any(not result.success for result in results):
        raise typer.Exit(1)
