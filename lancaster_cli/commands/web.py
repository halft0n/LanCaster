"""CLI command to start the Web UI."""

from __future__ import annotations

import asyncio
import signal

import click
from rich.console import Console


@click.command()
@click.option("--host", default=None, help="Bind address (default: auto-detect)")
@click.option("--port", "-p", default=8200, help="Web UI port (default: 8200)")
def web(host: str | None, port: int) -> None:
    """Start the Web UI for browser-based casting control."""
    console = Console()
    asyncio.run(_run_web(host, port, console))


async def _run_web(host: str | None, port: int, console: Console) -> None:
    from lancaster.web import WebServer

    server = WebServer(host=host, port=port)
    await server.start()

    console.print("\n[bold green]LanCaster Web UI[/bold green] running at:")
    console.print(f"  [link={server.base_url}]{server.base_url}[/link]\n")
    console.print("[dim]Press Ctrl+C to stop[/dim]\n")

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass

    try:
        await stop_event.wait()
    except KeyboardInterrupt:
        pass
    finally:
        console.print("\n[yellow]Shutting down...[/yellow]")
        await server.stop()
