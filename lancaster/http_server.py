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

_CHUNK_SIZE = 256 * 1024


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
        self._app.router.add_route(
            "HEAD", "/file/{file_id}", self._handle_file
        )
        self._app.router.add_route(
            "GET", "/stream/{stream_id}", self._handle_stream
        )
        self._app.router.add_route(
            "HEAD", "/stream/{stream_id}", self._handle_stream
        )

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

    def remove_file(self, file_id: str) -> None:
        """Unregister a served file."""
        self._files.pop(file_id, None)

    async def _handle_file(self, request: web.Request) -> web.StreamResponse:
        """Handle file requests with Range support (non-blocking reads)."""
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
            try:
                range_spec = range_header.replace("bytes=", "").strip()
                parts = range_spec.split("-")
                if not parts[0] and len(parts) > 1 and parts[1]:
                    suffix = int(parts[1])
                    start = max(0, file_size - suffix)
                    end = file_size - 1
                else:
                    if parts[0]:
                        start = int(parts[0])
                    if len(parts) > 1 and parts[1]:
                        end = int(parts[1])
            except (ValueError, IndexError):
                raise web.HTTPRequestRangeNotSatisfiable(
                    headers={
                        "Content-Range": f"bytes */{file_size}"
                    }
                )

            if start < 0 or start >= file_size or end < start:
                raise web.HTTPRequestRangeNotSatisfiable(
                    headers={
                        "Content-Range": f"bytes */{file_size}"
                    }
                )
            end = min(end, file_size - 1)

        content_length = end - start + 1
        status = 206 if range_header else 200

        headers = {
            "Content-Type": mime,
            "Content-Length": str(content_length),
            "Accept-Ranges": "bytes",
            "Connection": "keep-alive",
            "TransferMode.DLNA.ORG": "Streaming",
            "ContentFeatures.DLNA.ORG": (
                "DLNA.ORG_OP=01;"
                "DLNA.ORG_FLAGS="
                "01700000000000000000000000000000"
            ),
        }
        if range_header:
            headers["Content-Range"] = (
                f"bytes {start}-{end}/{file_size}"
            )

        response = web.StreamResponse(status=status, headers=headers)
        await response.prepare(request)

        if request.method == "HEAD":
            return response

        loop = asyncio.get_running_loop()
        remaining = content_length
        read_start = start

        while remaining > 0:
            read_size = min(_CHUNK_SIZE, remaining)
            data = await loop.run_in_executor(
                None, self._read_chunk, filepath, read_start, read_size
            )
            if not data:
                break
            try:
                await response.write(data)
            except (
                ConnectionResetError,
                ConnectionAbortedError,
                BrokenPipeError,
                asyncio.CancelledError,
            ):
                break
            remaining -= len(data)
            read_start += len(data)

        return response

    @staticmethod
    def _read_chunk(filepath: Path, offset: int, size: int) -> bytes:
        """Read a chunk from file (runs in thread pool)."""
        with open(filepath, "rb") as f:
            f.seek(offset)
            return f.read(size)

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
            if hasattr(stream, "read"):
                while True:
                    chunk = await stream.read(65536)
                    if not chunk:
                        break
                    await response.write(chunk)
            else:
                async for chunk in stream:
                    await response.write(chunk)
        except (
            ConnectionResetError,
            ConnectionAbortedError,
            BrokenPipeError,
            asyncio.CancelledError,
        ):
            pass

        return response
