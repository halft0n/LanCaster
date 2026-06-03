"""Tests for HTTP file server."""

import tempfile
from pathlib import Path

import aiohttp
import pytest

from lancaster.http_server import HTTPFileServer


@pytest.fixture
def temp_video():
    """Create a temporary file simulating a video."""
    content = b"FAKE_VIDEO_DATA_" * 1000
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        f.write(content)
        f.flush()
        yield Path(f.name), content


@pytest.mark.asyncio
async def test_serve_file_returns_url(temp_video):
    filepath, _ = temp_video
    server = HTTPFileServer(host="127.0.0.1", port=18200)
    url = server.serve_file(filepath)
    assert url.startswith("http://127.0.0.1:18200/file/")


@pytest.mark.asyncio
async def test_serve_same_file_returns_same_url(temp_video):
    filepath, _ = temp_video
    server = HTTPFileServer(host="127.0.0.1", port=18201)
    url1 = server.serve_file(filepath)
    url2 = server.serve_file(filepath)
    assert url1 == url2


@pytest.mark.asyncio
async def test_full_file_download(temp_video):
    filepath, content = temp_video
    server = HTTPFileServer(host="127.0.0.1", port=18202)
    await server.start()
    try:
        url = server.serve_file(filepath)
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                assert resp.status == 200
                body = await resp.read()
                assert body == content
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_range_request(temp_video):
    filepath, content = temp_video
    server = HTTPFileServer(host="127.0.0.1", port=18203)
    await server.start()
    try:
        url = server.serve_file(filepath)
        async with aiohttp.ClientSession() as session:
            headers = {"Range": "bytes=0-99"}
            async with session.get(url, headers=headers) as resp:
                assert resp.status == 206
                body = await resp.read()
                assert body == content[:100]
                assert "Content-Range" in resp.headers
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_head_request(temp_video):
    filepath, content = temp_video
    server = HTTPFileServer(host="127.0.0.1", port=18204)
    await server.start()
    try:
        url = server.serve_file(filepath)
        async with aiohttp.ClientSession() as session:
            async with session.head(url) as resp:
                assert resp.status == 200
                assert int(resp.headers["Content-Length"]) == len(content)
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_dlna_headers(temp_video):
    filepath, _ = temp_video
    server = HTTPFileServer(host="127.0.0.1", port=18205)
    await server.start()
    try:
        url = server.serve_file(filepath)
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                assert resp.headers.get("TransferMode.DLNA.ORG") == "Streaming"
                assert "DLNA.ORG_OP" in resp.headers.get("ContentFeatures.DLNA.ORG", "")
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_404_for_unknown_file():
    server = HTTPFileServer(host="127.0.0.1", port=18206)
    await server.start()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("http://127.0.0.1:18206/file/nonexistent") as resp:
                assert resp.status == 404
    finally:
        await server.stop()
