"""Playback control commands — pause, resume, stop, seek, volume, status."""

from __future__ import annotations

import asyncio
import sys

import click
from rich.console import Console

from lancaster.config import get_default_device
from lancaster.controller import MediaController
from lancaster.discovery import DeviceDiscovery
from lancaster.exceptions import LanCasterError
from lancaster.models import DeviceType
from lancaster.utils import format_duration, parse_duration


async def _find_renderer(device_name: str | None, timeout: float = 3.0):
    """Find a renderer device by name or use default/first available."""
    device_name = device_name or get_default_device()
    disc = DeviceDiscovery()
    devices = await disc.scan(timeout=timeout)
    renderers = [d for d in devices if d.device_type == DeviceType.RENDERER]

    if not renderers:
        return None

    if device_name:
        return disc.find_by_name(device_name)

    return renderers[0]


def _run_control(coro_factory, device_name: str | None) -> None:
    """Run a control coroutine with common error handling."""
    console = Console()
    try:
        asyncio.run(coro_factory(device_name, console))
    except KeyboardInterrupt:
        pass
    except LanCasterError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        sys.exit(1)


@click.command()
@click.option("-d", "--device", default=None, help="Device name.")
def pause(device: str | None) -> None:
    """Pause playback on the device."""

    async def _do(dev_name, console):
        renderer = await _find_renderer(dev_name)
        if not renderer:
            console.print("[red]No renderer found.[/red]")
            return
        ctrl = MediaController()
        await ctrl.pause(renderer)
        console.print(f"Paused on [bold]{renderer.name}[/bold]")

    _run_control(_do, device)


@click.command()
@click.option("-d", "--device", default=None, help="Device name.")
def resume(device: str | None) -> None:
    """Resume playback on the device."""

    async def _do(dev_name, console):
        renderer = await _find_renderer(dev_name)
        if not renderer:
            console.print("[red]No renderer found.[/red]")
            return
        ctrl = MediaController()
        await ctrl.resume(renderer)
        console.print(f"Resumed on [bold]{renderer.name}[/bold]")

    _run_control(_do, device)


@click.command()
@click.option("-d", "--device", default=None, help="Device name.")
def stop(device: str | None) -> None:
    """Stop playback on the device."""

    async def _do(dev_name, console):
        renderer = await _find_renderer(dev_name)
        if not renderer:
            console.print("[red]No renderer found.[/red]")
            return
        ctrl = MediaController()
        await ctrl.stop(renderer)
        console.print(f"Stopped on [bold]{renderer.name}[/bold]")

    _run_control(_do, device)


@click.command()
@click.argument("time")
@click.option("-d", "--device", default=None, help="Device name.")
def seek(time: str, device: str | None) -> None:
    """Seek to a position (e.g. 01:23:45 or 5:30)."""

    async def _do(dev_name, console):
        renderer = await _find_renderer(dev_name)
        if not renderer:
            console.print("[red]No renderer found.[/red]")
            return
        position = parse_duration(time)
        ctrl = MediaController()
        await ctrl.seek(renderer, position)
        console.print(f"Seeked to {format_duration(position)} on [bold]{renderer.name}[/bold]")

    _run_control(_do, device)


@click.command()
@click.argument("level", type=int)
@click.option("-d", "--device", default=None, help="Device name.")
def volume(level: int, device: str | None) -> None:
    """Set volume level (0-100)."""

    async def _do(dev_name, console):
        renderer = await _find_renderer(dev_name)
        if not renderer:
            console.print("[red]No renderer found.[/red]")
            return
        level_clamped = max(0, min(100, level))
        ctrl = MediaController()
        await ctrl.set_volume(renderer, level_clamped)
        console.print(f"Volume set to {level_clamped} on [bold]{renderer.name}[/bold]")

    _run_control(_do, device)


@click.command()
@click.option("-d", "--device", default=None, help="Device name.")
def status(device: str | None) -> None:
    """Show current playback status."""

    async def _do(dev_name, console):
        renderer = await _find_renderer(dev_name)
        if not renderer:
            console.print("[red]No renderer found.[/red]")
            return
        ctrl = MediaController()
        info = await ctrl.get_position(renderer)
        console.print(f"[bold]{renderer.name}[/bold]")
        console.print(f"  State:    {info.state.value}")
        pos = format_duration(info.position)
        dur = format_duration(info.duration)
        console.print(f"  Position: {pos} / {dur}")
        console.print(f"  Volume:   {info.volume}")
        if info.title:
            console.print(f"  Track:    {info.title}")

    _run_control(_do, device)
