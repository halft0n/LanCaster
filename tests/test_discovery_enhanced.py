"""Tests for enhanced device discovery (incremental merge, manual add, callbacks)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lancaster.discovery import DeviceDiscovery
from lancaster.models import DeviceType, DLNADevice


def _make_upnp_device(name="Smart TV", udn="uuid:tv1"):
    d = MagicMock()
    d.friendly_name = name
    d.manufacturer = "TestCorp"
    d.model_name = "Model-X"
    d.udn = udn
    d.services = {}
    return d


class TestIncrementalMerge:
    @pytest.mark.asyncio
    async def test_scan_does_not_clear_existing(self):
        disc = DeviceDiscovery(source_ip="192.168.1.1")
        existing_device = DLNADevice(
            name="Old TV",
            ip="192.168.1.50",
            location="http://192.168.1.50:49152/desc.xml",
            device_type=DeviceType.RENDERER,
            udn="uuid:old-tv",
        )
        disc._devices["uuid:old-tv"] = existing_device

        mock_listener = MagicMock()
        mock_listener.async_start = AsyncMock()
        mock_listener.async_search = AsyncMock()
        mock_listener.async_stop = AsyncMock()

        with (
            patch("lancaster.discovery.SsdpListener", return_value=mock_listener),
            patch("asyncio.sleep", new=AsyncMock()),
        ):
            await disc.scan(timeout=0.01)

        assert "uuid:old-tv" not in disc._devices

    @pytest.mark.asyncio
    async def test_scan_keeps_responding_devices(self):
        """Devices that respond during scan are kept (not evicted as stale)."""
        disc = DeviceDiscovery(source_ip="192.168.1.1")
        existing_device = DLNADevice(
            name="Existing TV",
            ip="192.168.1.50",
            location="http://192.168.1.50:49152/desc.xml",
            device_type=DeviceType.RENDERER,
            udn="uuid:existing",
        )
        disc._devices["uuid:existing"] = existing_device

        mock_listener = MagicMock()
        mock_listener.async_start = AsyncMock()
        mock_listener.async_search = AsyncMock()
        mock_listener.async_stop = AsyncMock()

        captured_callback = None

        def capture_listener(*args, **kwargs):
            nonlocal captured_callback
            captured_callback = kwargs.get("async_callback")
            return mock_listener

        with (
            patch(
                "lancaster.discovery.SsdpListener",
                side_effect=capture_listener,
            ),
            patch("asyncio.sleep", new=AsyncMock()),
            patch.object(disc, "_register_device", new=AsyncMock(return_value=existing_device)),
        ):
            # Simulate that the device re-announces during scan
            async def trigger_callback():
                if captured_callback:
                    ssdp = MagicMock()
                    ssdp.udn = "uuid:existing"
                    ssdp.location = "http://192.168.1.50:49152/desc.xml"
                    await captured_callback(ssdp, "MediaRenderer", MagicMock())

            mock_listener.async_search = AsyncMock(side_effect=trigger_callback)
            await disc.scan(timeout=0.01)

        assert "uuid:existing" in disc._devices


class TestLocationUpdate:
    @pytest.mark.asyncio
    async def test_device_location_updates(self):
        change_log = []

        def on_change(device, online):
            change_log.append((device.udn, online))

        disc = DeviceDiscovery(
            source_ip="192.168.1.1",
            on_device_change=on_change,
        )
        existing = DLNADevice(
            name="TV",
            ip="192.168.1.50",
            location="http://192.168.1.50:49152/desc.xml",
            device_type=DeviceType.RENDERER,
            udn="uuid:tv",
        )
        disc._devices["uuid:tv"] = existing

        ssdp_device = MagicMock()
        ssdp_device.location = "http://192.168.1.60:49152/desc.xml"
        ssdp_device.udn = "uuid:tv"

        result = await disc._register_device(ssdp_device, "MediaRenderer")
        assert result.ip == "192.168.1.60"
        assert result.location == "http://192.168.1.60:49152/desc.xml"
        assert ("uuid:tv", True) in change_log


class TestAddDeviceByLocation:
    @pytest.mark.asyncio
    async def test_add_success(self):
        disc = DeviceDiscovery(source_ip="192.168.1.1")

        mock_device = _make_upnp_device("Manual TV", "uuid:manual")
        with patch.object(
            disc._factory,
            "async_create_device",
            new=AsyncMock(return_value=mock_device),
        ):
            result = await disc.add_device_by_location("http://192.168.1.200:49152/desc.xml")

        assert result is not None
        assert result.name == "Manual TV"
        assert result.udn == "uuid:manual"
        assert "uuid:manual" in disc._devices

    @pytest.mark.asyncio
    async def test_add_failure_returns_none(self):
        disc = DeviceDiscovery(source_ip="192.168.1.1")
        with patch.object(
            disc._factory,
            "async_create_device",
            new=AsyncMock(side_effect=Exception("connect fail")),
        ):
            result = await disc.add_device_by_location("http://192.168.1.200:49152/desc.xml")

        assert result is None

    @pytest.mark.asyncio
    async def test_add_detects_server_type(self):
        disc = DeviceDiscovery(source_ip="192.168.1.1")

        mock_device = _make_upnp_device("NAS", "uuid:nas")
        mock_service = MagicMock()
        mock_service.service_type = "urn:schemas-upnp-org:service:ContentDirectory:1"
        mock_device.services = {"ContentDirectory": mock_service}

        with patch.object(
            disc._factory,
            "async_create_device",
            new=AsyncMock(return_value=mock_device),
        ):
            result = await disc.add_device_by_location("http://192.168.1.201:49152/desc.xml")

        assert result.device_type == DeviceType.SERVER


class TestDeviceChangeCallback:
    @pytest.mark.asyncio
    async def test_callback_on_new_device(self):
        change_log = []

        def on_change(device, online):
            change_log.append((device.name, online))

        disc = DeviceDiscovery(
            source_ip="192.168.1.1",
            on_device_change=on_change,
        )

        mock_device = _make_upnp_device("New TV", "uuid:new")
        ssdp_device = MagicMock()
        ssdp_device.location = "http://192.168.1.100:49152/desc.xml"
        ssdp_device.udn = "uuid:new"

        with patch.object(
            disc._factory,
            "async_create_device",
            new=AsyncMock(return_value=mock_device),
        ):
            await disc._register_device(
                ssdp_device,
                "urn:schemas-upnp-org:device:MediaRenderer:1",
            )

        assert ("New TV", True) in change_log

    def test_callback_not_called_without_handler(self):
        disc = DeviceDiscovery(source_ip="192.168.1.1")
        assert disc._on_device_change is None
