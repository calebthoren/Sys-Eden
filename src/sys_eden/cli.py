import asyncio
import json
import sqlite3
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError
from pydantic_settings import SettingsError
from sqlalchemy.exc import SQLAlchemyError

from sys_eden.config import load_settings
from sys_eden.core import Core
from sys_eden.inspection import collect
from sys_eden.inspection_format import render_human
from sys_eden.logging import configure_logging
from sys_eden.report_models import (
    ComponentTag,
    PurposeTag,
    ReportPriority,
    ReportSearch,
    ReportState,
    ReportStatus,
)
from sys_eden.report_repository import ReportNotFound, ReportRepository
from sys_eden.report_views import build_capsule, render_report, render_report_summary
from sys_eden.storage import Database, StorageError
from sys_eden.windows import WindowsCimReader
from sys_eden.windows_collectors import WindowsInspectionProvider

app = typer.Typer(
    name="eden",
    help="Sys Eden - local Windows system intelligence and maintenance.",
)
report_app = typer.Typer(help="Search and inspect durable structured reports.")
app.add_typer(report_app, name="report")


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
    supported = (
        "system",
        "cpu",
        "ram",
        "gpu",
        "storage",
        "network",
        "processes",
        "services",
        "startup",
        "drivers",
        "software",
        "events",
        "crashes",
        "boot",
    )
    if component != "all" and component not in supported:
        raise typer.BadParameter(
            "Supported components: all, system, cpu, ram, gpu, storage, network, "
            "processes, services, startup, drivers, software"
            ", events, crashes, boot"
        )

    async def run():
        reader = WindowsCimReader()
        provider = WindowsInspectionProvider(
            reader,
            software_reader=reader,
            event_reader=reader,
            graphics_reader=reader,
            service_dependency_reader=reader,
            network_statistics_reader=reader,
            wifi_quality_reader=reader,
            storage_trim_reader=reader,
        )
        names = supported if component == "all" else (component,)
        return [await collect(name, provider, details=details) for name in names]

    results = asyncio.run(run())
    if json_output:
        typer.echo(json.dumps([result.model_dump(mode="json") for result in results], indent=2))
    else:
        typer.echo("\n\n".join(render_human(result) for result in results))
    if any(not result.success for result in results):
        raise typer.Exit(1)


def _report_database() -> Database:
    database: Database | None = None
    try:
        settings = load_settings()
        database = Database(settings.data_directory / "eden.db")
        database.initialize()
        return database
    except (
        ValidationError,
        SettingsError,
        OSError,
        SQLAlchemyError,
        sqlite3.Error,
        StorageError,
    ) as error:
        if database is not None:
            database.close()
        typer.echo(f"Report storage unavailable: {type(error).__name__}", err=True)
        raise typer.Exit(1) from None


@report_app.command("list")
def report_list(
    query: Annotated[str | None, typer.Option("--query", "-q")] = None,
    state: Annotated[ReportState | None, typer.Option()] = None,
    status: Annotated[ReportStatus | None, typer.Option()] = None,
    priority: Annotated[ReportPriority | None, typer.Option()] = None,
    purpose: Annotated[PurposeTag | None, typer.Option()] = None,
    component: Annotated[ComponentTag | None, typer.Option()] = None,
    chain: Annotated[str | None, typer.Option()] = None,
    limit: Annotated[int, typer.Option(min=1, max=1000)] = 100,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """List reports using metadata-first search and filters."""
    database = _report_database()
    try:
        reports = ReportRepository(database).search(
            ReportSearch(
                query=query,
                state=state,
                status=status,
                priority=priority,
                purpose_tag=purpose,
                component_tag=component,
                chain_id=chain,
                limit=limit,
            )
        )
        if json_output:
            typer.echo(
                json.dumps(
                    [item.model_dump(mode="json") for item in reports], indent=2, sort_keys=True
                )
            )
        elif reports:
            typer.echo("\n".join(render_report_summary(item) for item in reports))
        else:
            typer.echo("No reports found.")
    finally:
        database.close()


@report_app.command("show")
def report_show(
    report_id: Annotated[str, typer.Argument()],
    capsule: Annotated[bool, typer.Option("--capsule")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Show a generated human view, compact AI capsule, or canonical JSON."""
    if capsule and json_output:
        raise typer.BadParameter("Choose either --capsule or --json")
    database = _report_database()
    try:
        try:
            report = ReportRepository(database).get(report_id)
        except ReportNotFound:
            typer.echo(f"Report not found: {report_id}", err=True)
            raise typer.Exit(1) from None
        if capsule:
            typer.echo(build_capsule(report).model_dump_json(indent=2))
        elif json_output:
            typer.echo(report.model_dump_json(indent=2))
        else:
            typer.echo(render_report(report))
    finally:
        database.close()


@report_app.command("export")
def report_export(
    report_id: Annotated[str, typer.Argument()],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Export the complete canonical report as portable JSON."""
    database = _report_database()
    try:
        try:
            payload = ReportRepository(database).get(report_id).model_dump_json(indent=2)
        except ReportNotFound:
            typer.echo(f"Report not found: {report_id}", err=True)
            raise typer.Exit(1) from None
        if output is None:
            typer.echo(payload)
            return
        try:
            with output.open("x", encoding="utf-8") as stream:
                stream.write(payload)
                stream.write("\n")
        except FileExistsError:
            typer.echo(f"Refusing to overwrite existing export: {output}", err=True)
            raise typer.Exit(1) from None
        typer.echo(f"Exported report to {output}")
    finally:
        database.close()
