"""CLI command to start the DLNA Media Server."""

from __future__ import annotations

import asyncio
import signal
from pathlib import Path

import click
from rich.console import Console

from lancaster.media_server import MediaServer


@click.command()
@click.argument("directories", nargs=-1, required=True, type=click.Path(exists=True))
@click.option("-p", "--port", default=8300, help="HTTP port (default: 8300).")
def serve(directories: tuple[str, ...], port: int) -> None:
    """Start a DLNA Media Server exposing local directories.

    The TV can browse and play files from the shared folders.

    \b
    Examples:
      lancaster serve ~/Movies ~/Music
      lancaster serve /mnt/media -p 9000
    """
    console = Console()
    try:
        asyncio.run(_serve(directories, port, console))
    except KeyboardInterrupt:
        console.print("\n[dim]Stopped.[/dim]")


async def _serve(directories: tuple[str, ...], port: int, console: Console) -> None:
    dirs = [Path(d) for d in directories]
    server = MediaServer(directories=dirs, port=port)
    server.scan()

    total_items = sum(
        1 for n in server.get_all_items() if not n.is_container
    )
    total_dirs = sum(
        1 for n in server.get_all_items() if n.is_container
    ) - 1

    console.print("\n[bold green]LanCaster Media Server[/bold green]")
    console.print(f"  Sharing: {', '.join(str(d) for d in dirs)}")
    console.print(f"  Found: {total_items} media files in {total_dirs} folders")
    console.print(f"  Port: {port}\n")
    console.print("[dim]Press Ctrl+C to stop[/dim]\n")

    stop_event = asyncio.Event()
    loop = asyncio.get_event_loop()
    try:
        loop.add_signal_handler(signal.SIGINT, stop_event.set)
    except NotImplementedError:
        pass

    await stop_event.wait()
