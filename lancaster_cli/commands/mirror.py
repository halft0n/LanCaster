"""CLI command for desktop mirroring."""

from __future__ import annotations

import asyncio
import signal
import sys

import click
from rich.console import Console

from lancaster.config import get_default_device
from lancaster.controller import MediaController
from lancaster.discovery import DeviceDiscovery
from lancaster.exceptions import LanCasterError
from lancaster.http_server import HTTPFileServer
from lancaster.mirror import DesktopMirror
from lancaster.models import DeviceType


@click.command()
@click.option("-d", "--device", default=None, help="Device name (partial match).")
@click.option("-t", "--timeout", default=5.0, help="Device scan timeout.")
@click.option("--fps", default=30, help="Frame rate (default: 30).")
@click.option(
    "--quality",
    type=click.Choice(["low", "medium", "high"]),
    default="medium",
    help="Quality preset.",
)
@click.option("--audio", is_flag=True, help="Capture system audio (experimental).")
def mirror(
    device: str | None,
    timeout: float,
    fps: int,
    quality: str,
    audio: bool,
) -> None:
    """Mirror your desktop to a DLNA device.

    Captures the screen via FFmpeg and streams to the TV as MPEG-TS.
    """
    console = Console()
    try:
        asyncio.run(_mirror(device, timeout, fps, quality, audio, console))
    except KeyboardInterrupt:
        console.print("\n[dim]Stopped.[/dim]")
    except LanCasterError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        sys.exit(1)


async def _mirror(
    device_name: str | None,
    timeout: float,
    fps: int,
    quality: str,
    audio: bool,
    console: Console,
) -> None:
    device_name = device_name or get_default_device()

    console.print(f"[bold]Scanning for devices ({timeout}s)...[/bold]")
    disc = DeviceDiscovery()
    devices = await disc.scan(timeout=timeout)

    renderers = [d for d in devices if d.device_type == DeviceType.RENDERER]
    if not renderers:
        console.print("[red]No DLNA renderers found.[/red]")
        return

    if device_name:
        dev = disc.find_by_name(device_name)
        if not dev:
            console.print(f"[red]Device '{device_name}' not found.[/red]")
            return
    else:
        dev = renderers[0]

    http_server = HTTPFileServer()
    await http_server.start()
    controller = MediaController(http_server=http_server)
    dm = DesktopMirror(http_server=http_server, controller=controller)

    console.print(f"Mirroring desktop to [bold]{dev.name}[/bold] ({quality}, {fps}fps)...")

    try:
        await dm.start(dev, fps=fps, quality=quality, audio=audio)
    except RuntimeError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        await http_server.stop()
        return

    console.print("[green]Mirroring![/green] Press Ctrl+C to stop.")

    stop_event = asyncio.Event()
    loop = asyncio.get_event_loop()
    try:
        loop.add_signal_handler(signal.SIGINT, stop_event.set)
    except NotImplementedError:
        pass

    await stop_event.wait()
    console.print("Stopping mirror...")
    await dm.stop()
    await http_server.stop()
