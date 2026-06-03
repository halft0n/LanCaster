"""Media playback controller (DMC role) for DLNA renderers."""

from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path

from async_upnp_client.aiohttp import AiohttpRequester
from async_upnp_client.client_factory import UpnpFactory
from async_upnp_client.profiles.dlna import DmrDevice

from lancaster.didl import DIDLBuilder
from lancaster.exceptions import DeviceConnectionError, PlaybackError
from lancaster.http_server import HTTPFileServer
from lancaster.models import DLNADevice, PlaybackInfo, TransportState
from lancaster.utils import guess_mime_type

_LOGGER = logging.getLogger(__name__)


class MediaController:
    """Control playback on a DLNA MediaRenderer device."""

    def __init__(self, http_server: HTTPFileServer | None = None) -> None:
        self._requester = AiohttpRequester(timeout=10)
        self._factory = UpnpFactory(self._requester, non_strict=True)
        self._http_server = http_server
        self._dmr_cache: dict[str, DmrDevice] = {}

    async def _get_dmr(self, device: DLNADevice) -> DmrDevice:
        """Get or create a DmrDevice for the given DLNA device."""
        if device.udn in self._dmr_cache:
            return self._dmr_cache[device.udn]

        try:
            upnp_device = await self._factory.async_create_device(device.location)
        except Exception as exc:
            raise DeviceConnectionError(
                f"Cannot connect to {device.name} at {device.location}"
            ) from exc

        dmr = DmrDevice(upnp_device, event_handler=None)
        self._dmr_cache[device.udn] = dmr
        return dmr

    async def play_url(
        self,
        device: DLNADevice,
        url: str,
        title: str | None = None,
        mime: str | None = None,
    ) -> None:
        """Cast a URL to the device for playback."""
        dmr = await self._get_dmr(device)
        media_title = title or "LanCaster Media"
        meta_data = DIDLBuilder.video_item(
            url=url,
            title=media_title,
            mime=mime or "video/mp4",
        )

        try:
            await dmr.async_set_transport_uri(url, media_title, meta_data=meta_data)
            await dmr.async_wait_for_can_play(max_wait_time=5)
            await dmr.async_play()
        except Exception as exc:
            raise PlaybackError(f"Failed to play URL on {device.name}: {exc}") from exc

        _LOGGER.info("Playing %s on %s", url, device.name)

    async def play_file(
        self,
        device: DLNADevice,
        filepath: str | Path,
        title: str | None = None,
        subtitle_path: str | Path | None = None,
    ) -> None:
        """Cast a local file to the device. Starts HTTP server if needed."""
        filepath = Path(filepath).resolve()
        if not filepath.exists():
            raise PlaybackError(f"File not found: {filepath}")

        if not self._http_server:
            raise PlaybackError("HTTP server is required for local file casting")

        file_url = self._http_server.serve_file(filepath)
        mime = guess_mime_type(filepath)
        media_title = title or filepath.stem

        subtitle_url = None
        if subtitle_path:
            subtitle_path = Path(subtitle_path).resolve()
            if subtitle_path.exists():
                subtitle_url = self._http_server.serve_file(subtitle_path)
        else:
            srt = filepath.with_suffix(".srt")
            if srt.exists():
                subtitle_url = self._http_server.serve_file(srt)

        meta_data = DIDLBuilder.video_item(
            url=file_url,
            title=media_title,
            mime=mime,
            subtitle_url=subtitle_url,
        )

        dmr = await self._get_dmr(device)
        try:
            await dmr.async_set_transport_uri(file_url, media_title, meta_data=meta_data)
            await dmr.async_wait_for_can_play(max_wait_time=5)
            await dmr.async_play()
        except Exception as exc:
            raise PlaybackError(f"Failed to play file on {device.name}: {exc}") from exc

        _LOGGER.info("Playing %s on %s", filepath.name, device.name)

    async def pause(self, device: DLNADevice) -> None:
        """Pause playback."""
        dmr = await self._get_dmr(device)
        try:
            await dmr.async_pause()
        except Exception as exc:
            raise PlaybackError(f"Failed to pause: {exc}") from exc

    async def resume(self, device: DLNADevice) -> None:
        """Resume playback."""
        dmr = await self._get_dmr(device)
        try:
            await dmr.async_play()
        except Exception as exc:
            raise PlaybackError(f"Failed to resume: {exc}") from exc

    async def stop(self, device: DLNADevice) -> None:
        """Stop playback."""
        dmr = await self._get_dmr(device)
        try:
            await dmr.async_stop()
        except Exception as exc:
            raise PlaybackError(f"Failed to stop: {exc}") from exc

    async def seek(self, device: DLNADevice, position: timedelta) -> None:
        """Seek to a specific position."""
        dmr = await self._get_dmr(device)
        try:
            await dmr.async_seek_abs_time(position)
        except Exception as exc:
            raise PlaybackError(f"Failed to seek: {exc}") from exc

    async def set_volume(self, device: DLNADevice, level: int) -> None:
        """Set volume (0-100)."""
        dmr = await self._get_dmr(device)
        try:
            action = dmr._action("RC", "SetVolume")
            if action:
                await action.async_call(InstanceID=0, Channel="Master", DesiredVolume=level)
        except Exception as exc:
            raise PlaybackError(f"Failed to set volume: {exc}") from exc

    async def get_volume(self, device: DLNADevice) -> int:
        """Get current volume level."""
        dmr = await self._get_dmr(device)
        try:
            action = dmr._action("RC", "GetVolume")
            if action:
                result = await action.async_call(InstanceID=0, Channel="Master")
                return int(result.get("CurrentVolume", 0))
        except Exception:
            pass
        return 0

    async def get_position(self, device: DLNADevice) -> PlaybackInfo:
        """Get current playback position and state."""
        dmr = await self._get_dmr(device)

        state = TransportState.STOPPED
        position = timedelta()
        duration = timedelta()
        title = ""

        try:
            action = dmr._action("AVT", "GetTransportInfo")
            if action:
                result = await action.async_call(InstanceID=0)
                raw_state = result.get("CurrentTransportState", "STOPPED")
                try:
                    state = TransportState(raw_state)
                except ValueError:
                    state = TransportState.STOPPED
        except Exception:
            pass

        try:
            action = dmr._action("AVT", "GetPositionInfo")
            if action:
                result = await action.async_call(InstanceID=0)
                position = self._parse_time(result.get("RelTime", "0:00:00"))
                duration = self._parse_time(result.get("TrackDuration", "0:00:00"))
                title = result.get("TrackURI", "")
        except Exception:
            pass

        volume = await self.get_volume(device)

        return PlaybackInfo(
            state=state,
            position=position,
            duration=duration,
            volume=volume,
            title=title,
        )

    @staticmethod
    def _parse_time(time_str: str) -> timedelta:
        """Parse UPnP time string (H:MM:SS or H:MM:SS.xxx) to timedelta."""
        if not time_str or time_str == "NOT_IMPLEMENTED":
            return timedelta()
        try:
            parts = time_str.split(":")
            h = int(parts[0]) if len(parts) > 0 else 0
            m = int(parts[1]) if len(parts) > 1 else 0
            s = float(parts[2]) if len(parts) > 2 else 0
            return timedelta(hours=h, minutes=m, seconds=s)
        except (ValueError, IndexError):
            return timedelta()
