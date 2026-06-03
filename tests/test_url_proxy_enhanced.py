"""Tests for URL proxy streaming download and size guard."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lancaster.models import DeviceType, DLNADevice
from lancaster.url_proxy import _MAX_DOWNLOAD_SIZE, URLProxy


def _make_device(name="Test TV"):
    return DLNADevice(
        name=name,
        ip="192.168.1.100",
        location="http://192.168.1.100:49152/description.xml",
        device_type=DeviceType.RENDERER,
        udn="uuid:test-tv",
    )


@pytest.fixture
def proxy():
    srv = MagicMock()
    srv.serve_file = MagicMock(return_value="http://192.168.1.50:8201/file/abc")
    ctrl = MagicMock()
    ctrl.play_url = AsyncMock()
    return URLProxy(http_server=srv, controller=ctrl)


class TestStreamDownload:
    @pytest.mark.asyncio
    async def test_downloads_to_disk(self, proxy, tmp_path):
        dest = tmp_path / "test.mp4"
        chunks = [b"a" * 64, b"b" * 64, b""]

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.content_length = 128

        async def fake_iter_chunked(size):
            for c in chunks:
                if c:
                    yield c

        mock_resp.content.iter_chunked = fake_iter_chunked
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "lancaster.url_proxy.aiohttp.ClientSession",
            return_value=mock_session,
        ):
            await proxy._stream_download("http://test.com/v.mp4", dest)

        assert dest.exists()
        assert dest.read_bytes() == b"a" * 64 + b"b" * 64

    @pytest.mark.asyncio
    async def test_rejects_too_large_content_length(self, proxy, tmp_path):
        dest = tmp_path / "huge.mp4"

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.content_length = _MAX_DOWNLOAD_SIZE + 1
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "lancaster.url_proxy.aiohttp.ClientSession",
            return_value=mock_session,
        ):
            with pytest.raises(ValueError, match="too large"):
                await proxy._stream_download("http://test.com/huge.mp4", dest)

    @pytest.mark.asyncio
    async def test_rejects_http_error(self, proxy, tmp_path):
        dest = tmp_path / "fail.mp4"

        mock_resp = MagicMock()
        mock_resp.status = 403
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "lancaster.url_proxy.aiohttp.ClientSession",
            return_value=mock_session,
        ):
            with pytest.raises(ConnectionError, match="403"):
                await proxy._stream_download("http://test.com/fail.mp4", dest)


class TestUUIDFilename:
    @pytest.mark.asyncio
    async def test_unique_filenames(self, proxy):
        device = _make_device()

        calls = []

        async def fake_stream_download(url, dest):
            calls.append(dest.name)
            dest.write_bytes(b"x")

        with (
            patch.object(proxy, "_stream_download", new=fake_stream_download),
            tempfile.TemporaryDirectory() as tmpdir,
            patch("lancaster.url_proxy._DOWNLOAD_DIR", Path(tmpdir)),
        ):
            await proxy.cast_proxied(device, "https://example.com/video.mp4")
            await proxy.cast_proxied(device, "https://example.com/video.mp4")

        assert calls[0] != calls[1]
        for name in calls:
            assert "video.mp4" in name
