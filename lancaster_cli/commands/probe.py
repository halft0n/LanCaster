"""CLI command to probe media file info via FFmpeg."""

from __future__ import annotations

import asyncio
import sys

import click
from rich.console import Console
from rich.table import Table

from lancaster.exceptions import TranscodeError
from lancaster.transcoder import Transcoder
from lancaster.utils import format_duration


@click.command()
@click.argument("filepath")
def probe(filepath: str) -> None:
    """Probe a media file and show codec/format info.

    Also reports whether transcoding is needed for DLNA compatibility.
    """
    console = Console()
    try:
        asyncio.run(_probe(filepath, console))
    except TranscodeError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        sys.exit(1)


async def _probe(filepath: str, console: Console) -> None:
    info = await Transcoder.probe(filepath)

    table = Table(title=f"Media Info: {filepath}", show_header=False)
    table.add_column("Property", style="bold")
    table.add_column("Value")

    table.add_row("Video Codec", info.video_codec or "(none)")
    table.add_row("Audio Codec", info.audio_codec or "(none)")
    table.add_row("Container", info.container)
    table.add_row("Resolution", f"{info.resolution[0]}x{info.resolution[1]}")
    table.add_row("Duration", format_duration(info.duration))
    table.add_row("Bitrate", f"{info.bitrate // 1000} kbps" if info.bitrate else "N/A")
    table.add_row("MIME Type", info.mime_type)
    if info.subtitle_tracks:
        table.add_row("Subtitles", ", ".join(info.subtitle_tracks))

    console.print(table)

    needs = Transcoder.needs_transcode(info)
    if needs:
        console.print("\n[yellow]This file needs transcoding for DLNA compatibility.[/yellow]")
        hw = await Transcoder.detect_hw_accel()
        if hw:
            console.print(f"  HW accelerators available: {', '.join(hw)}")
        else:
            console.print("  No HW acceleration detected, will use libx264.")
    else:
        console.print("\n[green]This file is DLNA-compatible, no transcoding needed.[/green]")
