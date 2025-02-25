import typer

from mcp_email_server.config import delete_settings

app = typer.Typer()


@app.command()
def stdio():
    typer.echo("🚧 STDIO not implemented yet")


@app.command()
def sse(
    host: str = "localhost",
    port: int = 9557,
):
    typer.echo("🚧 SSE not implemented yet")


@app.command()
def ui():
    typer.echo("🚧 UI not implemented yet")


@app.command()
def reset():
    delete_settings()
    typer.echo("✅ Config reset")
