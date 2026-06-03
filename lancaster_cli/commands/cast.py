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
from lancaster.transcoder import Transcoder
from lancaster.url_proxy import URLProxy


@click.command()
@click.argument("target")
@click.option("-d", "--device", default=None, help="Device name (partial match).")
@click.option("-t", "--timeout", default=5.0, help="Device scan timeout.")
@click.option("--no-transcode", is_flag=True, help="Skip auto-transcode check.")
@click.option("--force-proxy", is_flag=True, help="Force proxied mode for URLs.")
@click.option("--source-ip", default=None, help="Local IP for SSDP binding.")
def cast(
    target: str,
    device: str | None,
    timeout: float,
    no_transcode: bool,
    force_proxy: bool,
    source_ip: str | None,
) -> None:
    """Cast a local file or URL to a DLNA device.

    TARGET can be a local file path or an HTTP/HTTPS URL.
    Local files are auto-probed for DLNA compatibility.
    URLs are auto-routed (direct for HTTP, proxied for HTTPS).
    """
    console = Console()
    try:
        asyncio.run(_cast(target, device, timeout, no_transcode, force_proxy, source_ip, console))
    except KeyboardInterrupt:
        console.print("\n[dim]Stopped.[/dim]")
    except LanCasterError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        sys.exit(1)


async def _cast(
    target: str,
    device_name: str | None,
    timeout: float,
    no_transcode: bool,
    force_proxy: bool,
    source_ip: str | None,
    console: Console,
) -> None:
    device_name = device_name or get_default_device()

    console.print(f"[bold]Scanning for devices ({timeout}s)...[/bold]")
    disc = DeviceDiscovery(source_ip=source_ip)
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

    is_url = target.startswith(("http://", "https://"))

    if is_url:
        await _cast_url(target, dev, force_proxy, console)
    else:
        await _cast_file(target, dev, no_transcode, console)


async def _cast_url(target, dev, force_proxy, console):
    http_server = HTTPFileServer()
    await http_server.start()
    controller = MediaController(http_server=http_server)
    proxy = URLProxy(http_server=http_server, controller=controller)

    mode = "proxied" if force_proxy else URLProxy.detect_mode(target)
    console.print(f"Casting URL to [bold]{dev.name}[/bold] (mode: {mode})...")

    if force_proxy or mode == "proxied":
        await proxy.cast_proxied(dev, target)
    else:
        await proxy.cast_direct(dev, target)

    console.print("[green]Playing![/green] Press Ctrl+C to stop.")
    await _wait_for_stop(dev, controller, http_server, console)


async def _cast_file(target, dev, no_transcode, console):
    filepath = Path(target)
    if not filepath.exists():
        console.print(f"[red]File not found: {target}[/red]")
        return

    http_server = HTTPFileServer()
    await http_server.start()
    controller = MediaController(http_server=http_server)

    actual_file = filepath

    if not no_transcode:
        try:
            info = await Transcoder.probe(filepath)
            console.print(
                f"  Video: [cyan]{info.video_codec}[/cyan] | "
                f"Audio: [cyan]{info.audio_codec}[/cyan] | "
                f"Container: [cyan]{info.container}[/cyan]"
            )

            if Transcoder.needs_transcode(info):
                console.print("[yellow]File needs transcoding for DLNA compatibility.[/yellow]")
                transcode_dir = Path.home() / ".lancaster" / "transcoded"
                transcode_dir.mkdir(parents=True, exist_ok=True)
                output = transcode_dir / f"{filepath.stem}_dlna.mp4"

                hw = await Transcoder.detect_hw_accel()
                vcodec = hw[0] if hw else "libx264"
                console.print(f"  Transcoding with [bold]{vcodec}[/bold]...")

                t = Transcoder()
                actual_file = await t.transcode_to_file(
                    filepath,
                    output,
                    video_codec=vcodec,
                )
                console.print("[green]Transcode complete.[/green]")
            else:
                console.print("[green]File is DLNA-compatible.[/green]")
        except Exception as exc:
            console.print(f"[yellow]Probe/transcode skipped: {exc}[/yellow]")

    console.print(f"Casting [cyan]{actual_file.name}[/cyan] to [bold]{dev.name}[/bold]...")
    await controller.play_file(dev, actual_file)

    console.print("[green]Playing![/green] Press Ctrl+C to stop.")
    await _wait_for_stop(dev, controller, http_server, console)


async def _wait_for_stop(dev, controller, http_server, console):
    stop_event = asyncio.Event()
    loop = asyncio.get_event_loop()

    try:
        loop.add_signal_handler(signal.SIGINT, stop_event.set)
    except NotImplementedError:
        pass

    await stop_event.wait()
    console.print("Stopping playback...")
    try:
        await controller.stop(dev)
    except Exception:
        pass
    await http_server.stop()
