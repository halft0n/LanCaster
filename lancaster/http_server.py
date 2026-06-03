"""Embedded HTTP file server with Range support and DLNA headers."""

from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path
from typing import AsyncIterator

from aiohttp import web

from lancaster.utils import get_local_ip, guess_mime_type

_LOGGER = logging.getLogger(__name__)


class HTTPFileServer:
    """Serve local files and streams over HTTP for DLNA renderers to pull."""

    def __init__(self, host: str | None = None, port: int = 8200) -> None:
        self._host = host or get_local_ip()
        self._port = port
        self._app = web.Application()
        self._runner: web.AppRunner | None = None
        self._files: dict[str, Path] = {}
        self._streams: dict[str, AsyncIterator[bytes]] = {}
        self._app.router.add_route("GET", "/file/{file_id}", self._handle_file)
        self._app.router.add_route("HEAD", "/file/{file_id}", self._handle_file)
        self._app.router.add_route("GET", "/stream/{stream_id}", self._handle_stream)
        self._app.router.add_route("HEAD", "/stream/{stream_id}", self._handle_stream)

    @property
    def base_url(self) -> str:
        return f"http://{self._host}:{self._port}"

    async def start(self) -> None:
        """Start the HTTP server."""
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self._host, self._port)
        await site.start()
        _LOGGER.info("HTTP server listening on %s", self.base_url)

    async def stop(self) -> None:
        """Stop the HTTP server."""
        if self._runner:
            await self._runner.cleanup()
            self._runner = None

    def serve_file(self, filepath: str | Path) -> str:
        """Register a file and return its HTTP URL."""
        filepath = Path(filepath).resolve()
        for fid, existing in self._files.items():
            if existing == filepath:
                return f"{self.base_url}/file/{fid}"

        file_id = uuid.uuid4().hex[:12]
        self._files[file_id] = filepath
        url = f"{self.base_url}/file/{file_id}"
        _LOGGER.debug("Serving file %s at %s", filepath, url)
        return url

    def serve_stream(self, stream: AsyncIterator[bytes]) -> str:
        """Register a byte stream and return its HTTP URL."""
        stream_id = uuid.uuid4().hex[:12]
        self._streams[stream_id] = stream
        return f"{self.base_url}/stream/{stream_id}"

    async def _handle_file(self, request: web.Request) -> web.StreamResponse:
        """Handle file requests with Range support."""
        file_id = request.match_info["file_id"]
        filepath = self._files.get(file_id)
        if not filepath or not filepath.exists():
            raise web.HTTPNotFound()

        file_size = filepath.stat().st_size
        mime = guess_mime_type(filepath)

        range_header = request.headers.get("Range")
        start = 0
        end = file_size - 1

        if range_header:
            range_spec = range_header.replace("bytes=", "").strip()
            parts = range_spec.split("-")
            if parts[0]:
                start = int(parts[0])
            if parts[1]:
                end = int(parts[1])
            end = min(end, file_size - 1)

        content_length = end - start + 1
        status = 206 if range_header else 200

        headers = {
            "Content-Type": mime,
            "Content-Length": str(content_length),
            "Accept-Ranges": "bytes",
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Connection": "keep-alive",
            "TransferMode.DLNA.ORG": "Streaming",
            "ContentFeatures.DLNA.ORG": (
                "DLNA.ORG_OP=01;"
                "DLNA.ORG_FLAGS=01700000000000000000000000000000"
            ),
        }

        response = web.StreamResponse(status=status, headers=headers)
        await response.prepare(request)

        if request.method == "HEAD":
            return response

        chunk_size = 256 * 1024
        with open(filepath, "rb") as f:
            f.seek(start)
            remaining = content_length
            while remaining > 0:
                read_size = min(chunk_size, remaining)
                data = f.read(read_size)
                if not data:
                    break
                try:
                    await response.write(data)
                except ConnectionResetError:
                    break
                remaining -= len(data)

        return response

    async def _handle_stream(self, request: web.Request) -> web.StreamResponse:
        """Handle live stream requests (transcoded / mirrored content)."""
        stream_id = request.match_info["stream_id"]
        stream = self._streams.get(stream_id)
        if not stream:
            raise web.HTTPNotFound()

        headers = {
            "Content-Type": "video/mp2t",
            "TransferMode.DLNA.ORG": "Streaming",
            "Connection": "close",
        }

        response = web.StreamResponse(status=200, headers=headers)
        await response.prepare(request)

        if request.method == "HEAD":
            return response

        try:
            async for chunk in stream:
                await response.write(chunk)
        except (ConnectionResetError, asyncio.CancelledError):
            pass

        return response
