"""Tests for DeviceDiscovery, focusing on SSDP source binding."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lancaster.discovery import DeviceDiscovery


class TestResolveSource:
    """Verify _resolve_source binds to the correct interface."""

    def test_explicit_source_ip(self):
        disc = DeviceDiscovery(source_ip="192.168.1.42")
        assert disc._resolve_source() == ("192.168.1.42", 0)

    def test_auto_detect_lan_ip(self):
        disc = DeviceDiscovery()
        with patch("lancaster.discovery.get_local_ip", return_value="10.0.0.5"):
            result = disc._resolve_source()
        assert result == ("10.0.0.5", 0)

    def test_fallback_loopback_returns_none(self):
        disc = DeviceDiscovery()
        with patch("lancaster.discovery.get_local_ip", return_value="127.0.0.1"):
            result = disc._resolve_source()
        assert result is None

    def test_loopback_warns_on_windows(self):
        disc = DeviceDiscovery()
        with (
            patch("lancaster.discovery.get_local_ip", return_value="127.0.0.1"),
            patch("lancaster.discovery.sys") as mock_sys,
            patch("lancaster.discovery._LOGGER") as mock_logger,
        ):
            mock_sys.platform = "win32"
            disc._resolve_source()
            mock_logger.warning.assert_called_once()

    def test_explicit_ip_overrides_auto(self):
        disc = DeviceDiscovery(source_ip="172.16.0.1")
        with patch("lancaster.discovery.get_local_ip", return_value="10.0.0.5"):
            result = disc._resolve_source()
        assert result == ("172.16.0.1", 0)


class TestScanPassesSource:
    """Verify scan() and watch() pass source to SsdpListener."""

    @pytest.mark.asyncio
    async def test_scan_binds_source(self):
        disc = DeviceDiscovery(source_ip="192.168.1.10")
        mock_listener = MagicMock()
        mock_listener.async_start = AsyncMock()
        mock_listener.async_search = AsyncMock()
        mock_listener.async_stop = AsyncMock()

        with patch("lancaster.discovery.SsdpListener", return_value=mock_listener) as mock_cls:
            with patch("asyncio.sleep", new_callable=AsyncMock):
                await disc.scan(timeout=0.01)

            _, kwargs = mock_cls.call_args
            assert kwargs["source"] == ("192.168.1.10", 0)

    @pytest.mark.asyncio
    async def test_watch_binds_source(self):
        disc = DeviceDiscovery(source_ip="192.168.1.10")
        mock_listener = MagicMock()
        mock_listener.async_start = AsyncMock()
        mock_listener.async_search = AsyncMock()
        mock_listener.async_stop = AsyncMock()

        with patch("lancaster.discovery.SsdpListener", return_value=mock_listener) as mock_cls:
            await disc.watch()

            _, kwargs = mock_cls.call_args
            assert kwargs["source"] == ("192.168.1.10", 0)

    @pytest.mark.asyncio
    async def test_scan_default_auto_detect(self):
        disc = DeviceDiscovery()
        mock_listener = MagicMock()
        mock_listener.async_start = AsyncMock()
        mock_listener.async_search = AsyncMock()
        mock_listener.async_stop = AsyncMock()

        with (
            patch("lancaster.discovery.SsdpListener", return_value=mock_listener) as mock_cls,
            patch("lancaster.discovery.get_local_ip", return_value="10.0.0.99"),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            await disc.scan(timeout=0.01)
            _, kwargs = mock_cls.call_args
            assert kwargs["source"] == ("10.0.0.99", 0)


class TestClassify:
    """Verify device type classification."""

    def test_renderer_v1(self):
        from lancaster.models import DeviceType

        assert (
            DeviceDiscovery._classify("urn:schemas-upnp-org:device:MediaRenderer:1")
            == DeviceType.RENDERER
        )

    def test_server_v4(self):
        from lancaster.models import DeviceType

        assert (
            DeviceDiscovery._classify("urn:schemas-upnp-org:device:MediaServer:4")
            == DeviceType.SERVER
        )

    def test_avtransport_service(self):
        from lancaster.models import DeviceType

        assert (
            DeviceDiscovery._classify("urn:schemas-upnp-org:service:AVTransport:1")
            == DeviceType.RENDERER
        )

    def test_content_directory(self):
        from lancaster.models import DeviceType

        assert (
            DeviceDiscovery._classify("urn:schemas-upnp-org:service:ContentDirectory:1")
            == DeviceType.SERVER
        )

    def test_unknown_returns_none(self):
        assert DeviceDiscovery._classify("urn:schemas-upnp-org:device:Basic:1") is None
