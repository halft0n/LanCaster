"""URL proxy for online video casting with direct, proxied, and transcode modes."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from urllib.parse import urlparse

import aiohttp

from lancaster.controller import MediaController
from lancaster.http_server import HTTPFileServer
from lancaster.models import DLNADevice

_LOGGER = logging.getLogger(__name__)

_DOWNLOAD_DIR = Path.home() / ".lancaster" / "downloads"

_MAX_DOWNLOAD_SIZE = 10 * 1024 * 1024 * 1024  # 10 GB
_DOWNLOAD_CHUNK_SIZE = 64 * 1024  # 64 KB
_CLIENT_TIMEOUT = aiohttp.ClientTimeout(
    total=600, connect=15, sock_read=60
)


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
        """Download through PC (streaming chunks) and serve via local HTTP."""
        if not title:
            title = self.extract_filename(url)

        filename = f"{uuid.uuid4().hex[:8]}_{self.extract_filename(url)}"
        _DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        local_path = _DOWNLOAD_DIR / filename

        await self._stream_download(url, local_path)

        local_url = self._http_server.serve_file(local_path)
        await self._controller.play_url(device, local_url, title=title)

    async def _stream_download(self, url: str, dest: Path) -> None:
        """Download URL to disk in streaming chunks with size guard."""
        downloaded = 0
        try:
            async with aiohttp.ClientSession(
                timeout=_CLIENT_TIMEOUT
            ) as session:
                async with session.get(url) as resp:
                    if resp.status not in (200, 206):
                        raise ConnectionError(
                            f"Failed to download {url}: HTTP {resp.status}"
                        )

                    content_length = resp.content_length
                    if (
                        isinstance(content_length, int)
                        and content_length > _MAX_DOWNLOAD_SIZE
                    ):
                        raise ValueError(
                            f"File too large ({content_length} bytes, "
                            f"max {_MAX_DOWNLOAD_SIZE})"
                        )

                    with open(dest, "wb") as f:
                        async for chunk in resp.content.iter_chunked(
                            _DOWNLOAD_CHUNK_SIZE
                        ):
                            f.write(chunk)
                            downloaded += len(chunk)
                            if downloaded > _MAX_DOWNLOAD_SIZE:
                                raise ValueError(
                                    f"Download exceeded max size "
                                    f"({_MAX_DOWNLOAD_SIZE} bytes)"
                                )
        except Exception:
            dest.unlink(missing_ok=True)
            raise

        _LOGGER.info(
            "Downloaded %s -> %s (%d bytes)", url, dest.name, downloaded
        )
