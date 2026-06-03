"""Data models for LanCaster."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from enum import Enum


class DeviceType(str, Enum):
    RENDERER = "renderer"
    SERVER = "server"


class TransportState(str, Enum):
    PLAYING = "PLAYING"
    PAUSED = "PAUSED_PLAYBACK"
    STOPPED = "STOPPED"
    TRANSITIONING = "TRANSITIONING"
    NO_MEDIA = "NO_MEDIA_PRESENT"


@dataclass
class DLNADevice:
    """Represents a discovered DLNA device on the network."""

    name: str
    ip: str
    location: str
    device_type: DeviceType
    manufacturer: str = ""
    model: str = ""
    udn: str = ""

    def __str__(self) -> str:
        return f"{self.name} ({self.ip}) [{self.device_type.value}]"


@dataclass
class MediaInfo:
    """Media file metadata extracted via ffprobe."""

    path: str
    duration: timedelta = field(default_factory=timedelta)
    video_codec: str = ""
    audio_codec: str = ""
    container: str = ""
    resolution: tuple[int, int] = (0, 0)
    bitrate: int = 0
    subtitle_tracks: list[str] = field(default_factory=list)
    mime_type: str = "video/mp4"


@dataclass
class PlaybackInfo:
    """Current playback state of a renderer device."""

    state: TransportState = TransportState.STOPPED
    position: timedelta = field(default_factory=timedelta)
    duration: timedelta = field(default_factory=timedelta)
    volume: int = 0
    title: str = ""
