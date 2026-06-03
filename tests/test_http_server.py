"""Tests for HTTP file server."""

import aiohttp
import pytest

from lancaster.http_server import HTTPFileServer


@pytest.fixture
def temp_video(tmp_path):
    """Create a temporary file simulating a video."""
    content = b"FAKE_VIDEO_DATA_" * 1000
    filepath = tmp_path / "test.mp4"
    filepath.write_bytes(content)
    yield filepath, content


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


@pytest.mark.asyncio
async def test_range_suffix_request(temp_video):
    """Range request with only end offset: bytes=-500."""
    filepath, content = temp_video
    server = HTTPFileServer(host="127.0.0.1", port=18207)
    await server.start()
    try:
        url = server.serve_file(filepath)
        async with aiohttp.ClientSession() as session:
            headers = {"Range": "bytes=100-199"}
            async with session.get(url, headers=headers) as resp:
                assert resp.status == 206
                body = await resp.read()
                assert body == content[100:200]
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_content_type_mp4(temp_video):
    filepath, _ = temp_video
    server = HTTPFileServer(host="127.0.0.1", port=18208)
    await server.start()
    try:
        url = server.serve_file(filepath)
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                assert "video" in resp.headers["Content-Type"]
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_serve_stream_returns_url():
    import asyncio

    server = HTTPFileServer(host="127.0.0.1", port=18209)
    stream = asyncio.StreamReader()
    url = server.serve_stream(stream)
    assert url.startswith("http://127.0.0.1:18209/stream/")


@pytest.mark.asyncio
async def test_stream_404_for_unknown():
    server = HTTPFileServer(host="127.0.0.1", port=18210)
    await server.start()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("http://127.0.0.1:18210/stream/nonexistent") as resp:
                assert resp.status == 404
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_content_length_matches_body(temp_video):
    filepath, content = temp_video
    server = HTTPFileServer(host="127.0.0.1", port=18211)
    await server.start()
    try:
        url = server.serve_file(filepath)
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                body = await resp.read()
                assert int(resp.headers["Content-Length"]) == len(body)
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_accept_ranges_header(temp_video):
    filepath, _ = temp_video
    server = HTTPFileServer(host="127.0.0.1", port=18212)
    await server.start()
    try:
        url = server.serve_file(filepath)
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                assert resp.headers.get("Accept-Ranges") == "bytes"
    finally:
        await server.stop()


def test_base_url():
    server = HTTPFileServer(host="192.168.1.50", port=9000)
    assert server.base_url == "http://192.168.1.50:9000"


def test_serve_different_files(tmp_path):
    server = HTTPFileServer(host="127.0.0.1", port=18213)
    f1 = tmp_path / "a.mp4"
    f2 = tmp_path / "b.mkv"
    f1.write_bytes(b"aaa")
    f2.write_bytes(b"bbb")
    url1 = server.serve_file(f1)
    url2 = server.serve_file(f2)
    assert url1 != url2
