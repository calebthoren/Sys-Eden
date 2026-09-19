import asyncio
import json
from typing import Annotated

import typer
from pydantic import ValidationError
from pydantic_settings import SettingsError

from sys_eden.config import load_settings
from sys_eden.core import Core
from sys_eden.inspection import collect
from sys_eden.inspection_format import render_human
from sys_eden.logging import configure_logging
from sys_eden.windows import WindowsCimReader
from sys_eden.windows_collectors import WindowsInspectionProvider

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
def inspect(
    component: Annotated[str, typer.Argument()] = "system",
    details: Annotated[
        bool, typer.Option("--details", help="Show curated diagnostic and inventory fields.")
    ] = False,
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit the structured result as JSON.")
    ] = False,
) -> None:
    """Inspect local Windows state without changing the machine."""
    component = "system" if component == "os" else component
    supported = ("system", "cpu", "ram", "gpu", "storage", "network")
    if component != "all" and component not in supported:
        raise typer.BadParameter(
            "Supported components: all, system, cpu, ram, gpu, storage, network"
        )

    async def run():
        provider = WindowsInspectionProvider(WindowsCimReader())
        names = supported if component == "all" else (component,)
        return [await collect(name, provider, details=details) for name in names]

    results = asyncio.run(run())
    if json_output:
        typer.echo(json.dumps([result.model_dump(mode="json") for result in results], indent=2))
    else:
        typer.echo("\n\n".join(render_human(result) for result in results))
    if any(not result.success for result in results):
        raise typer.Exit(1)
