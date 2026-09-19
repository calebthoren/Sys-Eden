import typer

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
    typer.echo("Sys Eden")
    typer.echo("Core: OK")
