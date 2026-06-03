"""Device discovery command."""

from __future__ import annotations

import asyncio

import click
from rich.console import Console
from rich.table import Table

from lancaster.discovery import DeviceDiscovery


@click.command()
@click.option("-t", "--timeout", default=5.0, help="Scan timeout in seconds.")
@click.option(
    "--source-ip",
    default=None,
    help="Local IP to bind SSDP (for multi-NIC Windows, e.g. 192.168.1.100).",
)
def discover(timeout: float, source_ip: str | None) -> None:
    """Scan and list all DLNA devices on the network."""
    console = Console()
    console.print(f"[bold]Scanning for DLNA devices ({timeout}s)...[/bold]")

    devices = asyncio.run(_scan(timeout, source_ip))

    if not devices:
        console.print("[yellow]No DLNA devices found.[/yellow]")
        console.print("Make sure your PC and TV are on the same WiFi network.")
        console.print(
            "[dim]Tip: on Windows, try --source-ip <your-LAN-IP> "
            "if you have multiple network adapters.[/dim]"
        )
        return

    table = Table(title="DLNA Devices Found")
    table.add_column("#", style="dim", width=3)
    table.add_column("Name", style="bold")
    table.add_column("IP")
    table.add_column("Type")
    table.add_column("Manufacturer")
    table.add_column("Model")

    for i, dev in enumerate(devices, 1):
        table.add_row(
            str(i),
            dev.name,
            dev.ip,
            dev.device_type.value,
            dev.manufacturer,
            dev.model,
        )

    console.print(table)


async def _scan(timeout: float, source_ip: str | None = None):
    disc = DeviceDiscovery(source_ip=source_ip)
    return await disc.scan(timeout=timeout)
