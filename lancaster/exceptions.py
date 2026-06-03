"""Custom exceptions for LanCaster."""


class LanCasterError(Exception):
    """Base exception for all LanCaster errors."""


class DeviceNotFoundError(LanCasterError):
    """Raised when no matching DLNA device is found."""


class DeviceConnectionError(LanCasterError):
    """Raised when unable to connect to a DLNA device."""


class PlaybackError(LanCasterError):
    """Raised when a playback action fails."""


class TranscodeError(LanCasterError):
    """Raised when FFmpeg transcoding fails."""


class ServerError(LanCasterError):
    """Raised when the HTTP media server encounters an error."""
