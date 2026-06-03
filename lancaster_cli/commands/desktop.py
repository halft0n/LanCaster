"""CLI command to launch the desktop GUI."""

from __future__ import annotations

import sys

import click


@click.command()
@click.option("-p", "--port", default=8200, help="Web server port (default: 8200).")
def desktop(port: int) -> None:
    """Launch LanCaster as a desktop application.

    Opens a native window with the full Web UI, plus system tray icon.
    Requires: pip install lancaster[desktop]
    """
    try:
        import webview  # noqa: F401
    except ImportError:
        click.echo("Desktop mode requires pywebview.\nInstall with: pip install lancaster[desktop]")
        sys.exit(1)

    from lancaster.desktop import DesktopApp

    app = DesktopApp(port=port)
    app.run()
