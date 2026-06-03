"""DLNA device discovery via SSDP."""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Callable, Coroutine
from urllib.parse import urlparse

from async_upnp_client.aiohttp import AiohttpRequester
from async_upnp_client.client_factory import UpnpFactory
from async_upnp_client.ssdp_listener import SsdpDevice, SsdpListener, SsdpSource

from lancaster.models import DeviceType, DLNADevice
from lancaster.utils import get_local_ip

_LOGGER = logging.getLogger(__name__)

_RENDERER_TYPES = {
    "urn:schemas-upnp-org:device:MediaRenderer:1",
    "urn:schemas-upnp-org:device:MediaRenderer:2",
    "urn:schemas-upnp-org:device:MediaRenderer:3",
}

_SERVER_TYPES = {
    "urn:schemas-upnp-org:device:MediaServer:1",
    "urn:schemas-upnp-org:device:MediaServer:2",
    "urn:schemas-upnp-org:device:MediaServer:3",
    "urn:schemas-upnp-org:device:MediaServer:4",
}


class DeviceDiscovery:
    """Discover DLNA devices on the local network."""

    def __init__(self, source_ip: str | None = None) -> None:
        self._devices: dict[str, DLNADevice] = {}
        self._listener: SsdpListener | None = None
        self._requester = AiohttpRequester(timeout=10)
        self._factory = UpnpFactory(self._requester, non_strict=True)
        self._source_ip = source_ip

    def _resolve_source(self) -> tuple[str, int] | None:
        """Return (ip, 0) for SsdpListener source binding.

        On Windows, binding to 0.0.0.0 often fails to send multicast out
        the correct NIC when multiple adapters are present (VPN, Hyper-V,
        WSL, Docker).  Explicitly binding to the detected LAN IP fixes this.
        """
        ip = self._source_ip or get_local_ip()
        if ip and ip != "127.0.0.1":
            _LOGGER.debug("SSDP source bound to %s", ip)
            return (ip, 0)
        if sys.platform == "win32":
            _LOGGER.warning(
                "Could not detect LAN IP; SSDP may fail on Windows. Pass --source-ip explicitly."
            )
        return None

    async def scan(self, timeout: float = 5.0) -> list[DLNADevice]:
        """Scan for devices and return after timeout seconds."""
        self._devices.clear()

        async def _on_device(
            ssdp_device: SsdpDevice,
            dst: str,
            source: SsdpSource,
        ) -> None:
            await self._register_device(ssdp_device, dst)

        listener = SsdpListener(
            async_callback=_on_device,
            source=self._resolve_source(),
        )
        await listener.async_start()
        await listener.async_search()

        await asyncio.sleep(timeout)
        await listener.async_stop()

        return list(self._devices.values())

    async def watch(
        self,
        callback: Callable[[DLNADevice, bool], Coroutine] | None = None,
    ) -> SsdpListener:
        """Start continuous device monitoring. Returns the listener for later stop."""

        async def _on_device(
            ssdp_device: SsdpDevice,
            dst: str,
            source: SsdpSource,
        ) -> None:
            is_byebye = source == SsdpSource.ADVERTISEMENT_BYEBYE
            if is_byebye:
                udn = ssdp_device.udn
                if udn in self._devices:
                    removed = self._devices.pop(udn)
                    if callback:
                        await callback(removed, False)
                return

            device = await self._register_device(ssdp_device, dst)
            if device and callback:
                await callback(device, True)

        self._listener = SsdpListener(
            async_callback=_on_device,
            source=self._resolve_source(),
        )
        await self._listener.async_start()
        await self._listener.async_search()
        return self._listener

    async def stop_watch(self) -> None:
        """Stop the continuous watcher."""
        if self._listener:
            await self._listener.async_stop()
            self._listener = None

    async def _register_device(self, ssdp_device: SsdpDevice, dst: str) -> DLNADevice | None:
        """Fetch device description and register it."""
        location = ssdp_device.location
        if not location:
            return None

        udn = ssdp_device.udn
        if udn in self._devices:
            return self._devices[udn]

        device_type = self._classify(dst)
        if not device_type:
            return None

        try:
            upnp_device = await self._factory.async_create_device(location)
        except Exception:
            _LOGGER.debug("Failed to fetch description from %s", location, exc_info=True)
            return None

        parsed = urlparse(location)
        device = DLNADevice(
            name=upnp_device.friendly_name or "Unknown",
            ip=parsed.hostname or "",
            location=location,
            device_type=device_type,
            manufacturer=upnp_device.manufacturer or "",
            model=upnp_device.model_name or "",
            udn=udn,
        )
        self._devices[udn] = device
        _LOGGER.info("Discovered %s", device)
        return device

    @staticmethod
    def _classify(device_or_service_type: str) -> DeviceType | None:
        if device_or_service_type in _RENDERER_TYPES:
            return DeviceType.RENDERER
        if device_or_service_type in _SERVER_TYPES:
            return DeviceType.SERVER
        if "AVTransport" in device_or_service_type:
            return DeviceType.RENDERER
        if "ContentDirectory" in device_or_service_type:
            return DeviceType.SERVER
        return None

    def find_by_name(self, name: str) -> DLNADevice | None:
        """Find a cached device by (partial) name match."""
        name_lower = name.lower()
        for d in self._devices.values():
            if name_lower in d.name.lower():
                return d
        return None

    def find_by_ip(self, ip: str) -> DLNADevice | None:
        """Find a cached device by IP address."""
        for d in self._devices.values():
            if d.ip == ip:
                return d
        return None

    @property
    def devices(self) -> list[DLNADevice]:
        return list(self._devices.values())

    @property
    def renderers(self) -> list[DLNADevice]:
        return [d for d in self._devices.values() if d.device_type == DeviceType.RENDERER]

    @property
    def servers(self) -> list[DLNADevice]:
        return [d for d in self._devices.values() if d.device_type == DeviceType.SERVER]
