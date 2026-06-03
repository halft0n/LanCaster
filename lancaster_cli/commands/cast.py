"""Cast command — send local files or URLs to a DLNA renderer."""

from __future__ import annotations

import asyncio
import signal
import sys
from pathlib import Path

import click
from rich.console import Console

from lancaster.config import get_default_device
from lancaster.controller import MediaController
from lancaster.discovery import DeviceDiscovery
from lancaster.exceptions import LanCasterError
from lancaster.http_server import HTTPFileServer
from lancaster.models import DeviceType


@click.command()
@click.argument("target")
@click.option("-d", "--device", default=None, help="Device name (partial match).")
@click.option("-t", "--timeout", default=5.0, help="Device scan timeout.")
def cast(target: str, device: str | None, timeout: float) -> None:
    """Cast a local file or URL to a DLNA device.

    TARGET can be a local file path or an HTTP/HTTPS URL.
    """
    console = Console()
    try:
        asyncio.run(_cast(target, device, timeout, console))
    except KeyboardInterrupt:
        console.print("\n[dim]Stopped.[/dim]")
    except LanCasterError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        sys.exit(1)


async def _cast(target: str, device_name: str | None, timeout: float, console: Console) -> None:
    device_name = device_name or get_default_device()

    console.print(f"[bold]Scanning for devices ({timeout}s)...[/bold]")
    disc = DeviceDiscovery()
    devices = await disc.scan(timeout=timeout)

    renderers = [d for d in devices if d.device_type == DeviceType.RENDERER]
    if not renderers:
        console.print("[red]No DLNA renderers found on the network.[/red]")
        return

    if device_name:
        dev = disc.find_by_name(device_name)
        if not dev:
            console.print(f"[red]Device '{device_name}' not found.[/red]")
            console.print("Available renderers:")
            for r in renderers:
                console.print(f"  - {r.name} ({r.ip})")
            return
    else:
        dev = renderers[0]
        if len(renderers) > 1:
            console.print(f"[yellow]Multiple renderers found, using: {dev.name}[/yellow]")
            console.print("Use -d to specify a device.")

    is_url = target.startswith("http://") or target.startswith("https://")

    if is_url:
        console.print(f"Casting URL to [bold]{dev.name}[/bold]...")
        controller = MediaController()
        await controller.play_url(dev, target, title="LanCaster Stream")
    else:
        filepath = Path(target)
        if not filepath.exists():
            console.print(f"[red]File not found: {target}[/red]")
            return

        http_server = HTTPFileServer()
        await http_server.start()

        controller = MediaController(http_server=http_server)
        console.print(f"Casting [cyan]{filepath.name}[/cyan] to [bold]{dev.name}[/bold]...")
        await controller.play_file(dev, filepath)

        console.print("[green]Playing![/green] Press Ctrl+C to stop.")

        stop_event = asyncio.Event()
        loop = asyncio.get_event_loop()

        def _on_signal() -> None:
            stop_event.set()

        try:
            loop.add_signal_handler(signal.SIGINT, _on_signal)
        except NotImplementedError:
            pass

        await stop_event.wait()

        console.print("Stopping playback...")
        try:
            await controller.stop(dev)
        except Exception:
            pass
        await http_server.stop()
