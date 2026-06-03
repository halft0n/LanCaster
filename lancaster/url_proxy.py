"""URL proxy for online video casting with direct, proxied, and transcode modes."""

from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import urlparse

import aiohttp

from lancaster.controller import MediaController
from lancaster.http_server import HTTPFileServer
from lancaster.models import DLNADevice

_LOGGER = logging.getLogger(__name__)

_UPLOAD_DIR = Path.home() / ".lancaster" / "downloads"

_DIRECT_EXTENSIONS = {
    ".mp4",
    ".m4v",
    ".mkv",
    ".avi",
    ".mov",
    ".ts",
    ".mp3",
    ".m4a",
    ".flac",
    ".wav",
    ".m3u8",
}


class URLProxy:
    """Handle online URL casting with automatic mode selection."""

    def __init__(
        self,
        http_server: HTTPFileServer,
        controller: MediaController,
    ) -> None:
        self._http_server = http_server
        self._controller = controller

    @staticmethod
    def detect_mode(url: str) -> str:
        """Determine the best casting mode for a URL.

        Returns "direct" for plain HTTP media URLs that TVs can fetch directly,
        or "proxied" for HTTPS or non-standard URLs requiring PC relay.
        """
        if not url:
            return "proxied"
        parsed = urlparse(url)
        if parsed.scheme == "http":
            return "direct"
        return "proxied"

    @staticmethod
    def extract_filename(url: str) -> str:
        """Extract a human-readable filename from a URL."""
        parsed = urlparse(url)
        path = parsed.path.rstrip("/")
        if "/" in path:
            return path.rsplit("/", 1)[-1]
        return path or "media"

    async def auto_cast(
        self,
        device: DLNADevice,
        url: str,
        title: str | None = None,
    ) -> None:
        """Automatically choose direct or proxied mode and cast."""
        if device is None:
            raise ValueError("No device specified")

        mode = self.detect_mode(url)
        _LOGGER.info("URL cast mode: %s for %s", mode, url)

        if mode == "direct":
            await self.cast_direct(device, url, title=title)
        else:
            await self.cast_proxied(device, url, title=title)

    async def cast_direct(
        self,
        device: DLNADevice,
        url: str,
        title: str | None = None,
    ) -> None:
        """Send the URL directly to the TV (TV fetches from internet)."""
        if not title:
            title = self.extract_filename(url)
        await self._controller.play_url(device, url, title=title)

    async def cast_proxied(
        self,
        device: DLNADevice,
        url: str,
        title: str | None = None,
    ) -> None:
        """Download through PC and serve via local HTTP server."""
        if not title:
            title = self.extract_filename(url)

        filename = self.extract_filename(url)
        _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        local_path = _UPLOAD_DIR / filename

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    raise ConnectionError(f"Failed to download {url}: HTTP {resp.status}")
                data = await resp.read()
                local_path.write_bytes(data)

        local_url = await self._http_server.serve_file(local_path)
        await self._controller.play_url(device, local_url, title=title)
