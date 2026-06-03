"""Tests for the URLProxy module (TDD — written before implementation)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lancaster.models import DeviceType, DLNADevice
from lancaster.url_proxy import URLProxy


def _make_device(name="Test TV"):
    return DLNADevice(
        name=name,
        ip="192.168.1.100",
        location="http://192.168.1.100:49152/description.xml",
        device_type=DeviceType.RENDERER,
    )


@pytest.fixture
def mock_http_server():
    srv = MagicMock()
    srv.serve_stream = MagicMock(return_value="http://192.168.1.50:8201/stream/abc")
    srv.serve_file = MagicMock(return_value="http://192.168.1.50:8201/files/dl.mp4")
    return srv


@pytest.fixture
def mock_controller():
    ctrl = MagicMock()
    ctrl.play_url = AsyncMock()
    return ctrl


@pytest.fixture
def proxy(mock_http_server, mock_controller):
    return URLProxy(
        http_server=mock_http_server,
        controller=mock_controller,
    )


# === Mode Detection ===


class TestDetectMode:
    def test_http_mp4_direct(self):
        assert URLProxy.detect_mode("http://example.com/video.mp4") == "direct"

    def test_http_mkv_direct(self):
        assert URLProxy.detect_mode("http://example.com/video.mkv") == "direct"

    def test_http_m3u8_direct(self):
        assert URLProxy.detect_mode("http://example.com/live.m3u8") == "direct"

    def test_https_mp4_proxied(self):
        assert URLProxy.detect_mode("https://example.com/video.mp4") == "proxied"

    def test_https_random_proxied(self):
        assert URLProxy.detect_mode("https://cdn.example.com/path?token=abc") == "proxied"

    def test_http_with_query_direct(self):
        assert URLProxy.detect_mode("http://example.com/video.mp4?key=123") == "direct"

    def test_ftp_proxied(self):
        """Non-HTTP protocols should use proxied mode."""
        assert URLProxy.detect_mode("ftp://example.com/video.mp4") == "proxied"

    def test_empty_url_proxied(self):
        assert URLProxy.detect_mode("") == "proxied"


# === Auto Cast ===


class TestAutoCast:
    @pytest.mark.asyncio
    async def test_auto_direct(self, proxy, mock_controller):
        """HTTP URL should use direct mode by default."""
        device = _make_device()
        await proxy.auto_cast(device, "http://example.com/movie.mp4")
        mock_controller.play_url.assert_awaited_once()
        call_args = mock_controller.play_url.call_args
        assert call_args[0][1] == "http://example.com/movie.mp4"

    @pytest.mark.asyncio
    async def test_auto_proxied(self, proxy, mock_controller, mock_http_server):
        """HTTPS URL should be proxied through local server."""
        device = _make_device()

        with patch("lancaster.url_proxy.aiohttp.ClientSession") as mock_session_cls:
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.read = AsyncMock(return_value=b"\x00" * 100)
            mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_resp.__aexit__ = AsyncMock(return_value=False)

            mock_session = MagicMock()
            mock_session.get = MagicMock(return_value=mock_resp)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_session_cls.return_value = mock_session

            await proxy.auto_cast(device, "https://cdn.example.com/video.mp4")

        mock_controller.play_url.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_auto_no_device_raises(self, proxy):
        """Casting to None device should raise."""
        with pytest.raises((ValueError, AttributeError)):
            await proxy.auto_cast(None, "http://example.com/v.mp4")


# === Direct Cast ===


class TestDirectCast:
    @pytest.mark.asyncio
    async def test_cast_direct(self, proxy, mock_controller):
        device = _make_device()
        await proxy.cast_direct(device, "http://example.com/movie.mp4")
        mock_controller.play_url.assert_awaited_once_with(
            device,
            "http://example.com/movie.mp4",
            title="movie.mp4",
        )


# === Proxied Cast ===


class TestProxiedCast:
    @pytest.mark.asyncio
    async def test_cast_proxied(self, proxy, mock_controller, mock_http_server):
        """Proxied cast should download and serve through local HTTP."""
        device = _make_device()

        with patch("aiohttp.ClientSession") as mock_session_cls:
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.headers = {"Content-Type": "video/mp4"}

            async def fake_read():
                return b"\x00" * 1000

            mock_resp.read = fake_read
            mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_resp.__aexit__ = AsyncMock(return_value=False)

            mock_session = MagicMock()
            mock_session.get = MagicMock(return_value=mock_resp)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_session_cls.return_value = mock_session

            await proxy.cast_proxied(
                device,
                "https://cdn.example.com/video.mp4",
            )

        mock_controller.play_url.assert_awaited_once()


# === URL Parsing ===


class TestURLParsing:
    def test_extract_filename_simple(self):
        assert URLProxy.extract_filename("http://example.com/movie.mp4") == "movie.mp4"

    def test_extract_filename_with_query(self):
        name = URLProxy.extract_filename(
            "http://example.com/movie.mp4?token=abc&q=1",
        )
        assert name == "movie.mp4"

    def test_extract_filename_no_extension(self):
        name = URLProxy.extract_filename("http://example.com/stream")
        assert name == "stream"

    def test_extract_filename_complex_path(self):
        name = URLProxy.extract_filename(
            "https://cdn.example.com/path/to/video_1080p.mp4",
        )
        assert name == "video_1080p.mp4"
