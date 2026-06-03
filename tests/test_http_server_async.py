"""Tests for HTTP file server async improvements."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from aiohttp.test_utils import TestClient, TestServer

from lancaster.http_server import HTTPFileServer


@pytest.fixture
def http_server():
    return HTTPFileServer(host="127.0.0.1", port=9999)


class TestServeFile:
    def test_returns_url(self, http_server):
        with patch.object(Path, "resolve", return_value=Path("/tmp/video.mp4")):
            url = http_server.serve_file("/tmp/video.mp4")
        assert url.startswith("http://127.0.0.1:9999/file/")

    def test_same_file_same_url(self, http_server):
        p = Path("/tmp/same.mp4")
        with patch.object(Path, "resolve", return_value=p):
            url1 = http_server.serve_file(p)
            url2 = http_server.serve_file(p)
        assert url1 == url2

    def test_different_files_different_urls(self, http_server):
        with patch.object(Path, "resolve", side_effect=[
            Path("/tmp/a.mp4"), Path("/tmp/b.mp4")
        ]):
            url1 = http_server.serve_file("/tmp/a.mp4")
        with patch.object(Path, "resolve", return_value=Path("/tmp/b.mp4")):
            url2 = http_server.serve_file("/tmp/b.mp4")
        assert url1 != url2


class TestServeStream:
    def test_returns_url(self, http_server):
        async def fake_stream():
            yield b"data"

        url = http_server.serve_stream(fake_stream())
        assert "/stream/" in url


class TestReadChunk:
    def test_reads_correct_chunk(self, tmp_path):
        f = tmp_path / "data.bin"
        f.write_bytes(b"0123456789abcdef")

        chunk = HTTPFileServer._read_chunk(f, 4, 6)
        assert chunk == b"456789"

    def test_reads_from_start(self, tmp_path):
        f = tmp_path / "data.bin"
        f.write_bytes(b"ABCDEFGH")

        chunk = HTTPFileServer._read_chunk(f, 0, 3)
        assert chunk == b"ABC"


class TestRangeValidation:
    @pytest.mark.asyncio
    async def test_invalid_range_returns_416(self, tmp_path):
        srv = HTTPFileServer(host="127.0.0.1", port=9998)
        f = tmp_path / "test.mp4"
        f.write_bytes(b"x" * 100)
        srv.serve_file(f)

        file_id = list(srv._files.keys())[0]

        app = srv._app
        async with TestClient(TestServer(app)) as client:
            resp = await client.get(
                f"/file/{file_id}",
                headers={"Range": "bytes=200-300"},
            )
            assert resp.status == 416

    @pytest.mark.asyncio
    async def test_valid_range_returns_206(self, tmp_path):
        srv = HTTPFileServer(host="127.0.0.1", port=9997)
        f = tmp_path / "test.mp4"
        f.write_bytes(b"x" * 100)
        srv.serve_file(f)

        file_id = list(srv._files.keys())[0]

        app = srv._app
        async with TestClient(TestServer(app)) as client:
            resp = await client.get(
                f"/file/{file_id}",
                headers={"Range": "bytes=0-49"},
            )
            assert resp.status == 206
            assert resp.headers["Content-Range"] == "bytes 0-49/100"
            body = await resp.read()
            assert len(body) == 50

    @pytest.mark.asyncio
    async def test_no_range_returns_200(self, tmp_path):
        srv = HTTPFileServer(host="127.0.0.1", port=9996)
        f = tmp_path / "test.mp4"
        f.write_bytes(b"hello world")
        srv.serve_file(f)

        file_id = list(srv._files.keys())[0]

        app = srv._app
        async with TestClient(TestServer(app)) as client:
            resp = await client.get(f"/file/{file_id}")
            assert resp.status == 200
            assert "Content-Range" not in resp.headers
            body = await resp.read()
            assert body == b"hello world"

    @pytest.mark.asyncio
    async def test_head_request(self, tmp_path):
        srv = HTTPFileServer(host="127.0.0.1", port=9995)
        f = tmp_path / "test.mp4"
        f.write_bytes(b"x" * 500)
        srv.serve_file(f)

        file_id = list(srv._files.keys())[0]

        app = srv._app
        async with TestClient(TestServer(app)) as client:
            resp = await client.head(f"/file/{file_id}")
            assert resp.status == 200
            assert resp.headers["Content-Length"] == "500"
