"""LanCaster CLI main entry point."""

from __future__ import annotations

import click

from lancaster_cli.commands.cast import cast
from lancaster_cli.commands.control import pause, resume, seek, status, stop, volume
from lancaster_cli.commands.discover import discover
from lancaster_cli.commands.web import web


@click.group()
@click.version_option(package_name="lancaster")
def main() -> None:
    """LanCaster - Cast videos to your TV via DLNA."""


main.add_command(discover)
main.add_command(cast)
main.add_command(pause)
main.add_command(resume)
main.add_command(stop)
main.add_command(seek)
main.add_command(volume)
main.add_command(status)
main.add_command(web)


if __name__ == "__main__":
    main()
