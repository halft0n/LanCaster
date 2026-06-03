"""Network and general utilities."""

from __future__ import annotations

import mimetypes
import socket
from pathlib import Path


def get_local_ip(target_ip: str = "8.8.8.8") -> str:
    """Detect the local LAN IP address by connecting to a target.

    Uses a UDP socket trick: connect() on a UDP socket doesn't actually
    send data but lets the OS pick the correct source interface.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect((target_ip, 80))
            return s.getsockname()[0]
        except OSError:
            return "127.0.0.1"


def guess_mime_type(filepath: str | Path) -> str:
    """Guess MIME type from file extension."""
    ext_map = {
        ".mp4": "video/mp4",
        ".mkv": "video/x-matroska",
        ".avi": "video/x-msvideo",
        ".mov": "video/quicktime",
        ".wmv": "video/x-ms-wmv",
        ".flv": "video/x-flv",
        ".webm": "video/webm",
        ".ts": "video/mp2t",
        ".m4v": "video/x-m4v",
        ".mpg": "video/mpeg",
        ".mpeg": "video/mpeg",
        ".mp3": "audio/mpeg",
        ".flac": "audio/flac",
        ".wav": "audio/wav",
        ".aac": "audio/aac",
        ".ogg": "audio/ogg",
        ".srt": "text/srt",
    }
    suffix = Path(filepath).suffix.lower()
    if suffix in ext_map:
        return ext_map[suffix]

    mime, _ = mimetypes.guess_type(str(filepath))
    return mime or "application/octet-stream"


def format_duration(td: __import__("datetime").timedelta) -> str:
    """Format a timedelta as HH:MM:SS."""
    total = int(td.total_seconds())
    hours, remainder = divmod(total, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def parse_duration(s: str) -> __import__("datetime").timedelta:
    """Parse HH:MM:SS or MM:SS into a timedelta."""
    from datetime import timedelta

    parts = s.split(":")
    if len(parts) == 3:
        h, m, sec = int(parts[0]), int(parts[1]), float(parts[2])
    elif len(parts) == 2:
        h, m, sec = 0, int(parts[0]), float(parts[1])
    else:
        h, m, sec = 0, 0, float(parts[0])
    return timedelta(hours=h, minutes=m, seconds=sec)
