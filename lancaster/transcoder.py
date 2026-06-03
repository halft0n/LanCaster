"""FFmpeg-based media probing and transcoding."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path

from lancaster.exceptions import TranscodeError
from lancaster.models import MediaInfo

_LOGGER = logging.getLogger(__name__)

SAFE_VIDEO_CODECS = {"h264", "mpeg4", "mpeg2video"}
SAFE_AUDIO_CODECS = {"aac", "mp3", "ac3", "eac3", "pcm_s16le", "flac"}
SAFE_CONTAINERS = {"mp4", "mov,mp4,m4a,3gp,3g2,mj2", "mp3", "wav", "flac", "aac"}

HW_ENCODERS = ("h264_nvenc", "h264_qsv", "h264_amf")


class Transcoder:
    """Probe media files and transcode via FFmpeg subprocess."""

    @staticmethod
    async def probe(filepath: Path) -> MediaInfo:
        """Extract media metadata using ffprobe."""
        filepath = Path(filepath)
        if not filepath.exists():
            raise TranscodeError(f"File not found: {filepath}")

        try:
            proc = await asyncio.create_subprocess_exec(
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_format", "-show_streams",
                str(filepath),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
        except FileNotFoundError:
            raise TranscodeError(
                "ffprobe not found. Please install FFmpeg."
            ) from None

        if proc.returncode != 0:
            raise TranscodeError(
                f"ffprobe failed (exit {proc.returncode}): "
                f"{stderr.decode(errors='replace').strip()}"
            )

        try:
            data = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise TranscodeError(f"Failed to parse ffprobe output: {exc}") from exc

        return Transcoder._parse_probe(data, str(filepath))

    @staticmethod
    def _parse_probe(data: dict, path: str) -> MediaInfo:
        """Parse ffprobe JSON into a MediaInfo object."""
        streams = data.get("streams", [])
        fmt = data.get("format", {})

        video_codec = ""
        audio_codec = ""
        width, height = 0, 0
        bitrate = 0
        subtitle_tracks = []

        for s in streams:
            codec_type = s.get("codec_type", "")
            if codec_type == "video" and not video_codec:
                video_codec = s.get("codec_name", "")
                width = int(s.get("width", 0))
                height = int(s.get("height", 0))
                if s.get("bit_rate"):
                    bitrate = int(s["bit_rate"])
            elif codec_type == "audio" and not audio_codec:
                audio_codec = s.get("codec_name", "")
            elif codec_type == "subtitle":
                subtitle_tracks.append(s.get("codec_name", "unknown"))

        duration_str = fmt.get("duration", "0")
        try:
            duration = timedelta(seconds=float(duration_str))
        except (ValueError, TypeError):
            duration = timedelta()

        if not bitrate and fmt.get("bit_rate"):
            try:
                bitrate = int(fmt["bit_rate"])
            except (ValueError, TypeError):
                pass

        container = fmt.get("format_name", "")

        from lancaster.utils import guess_mime_type
        mime_type = guess_mime_type(path)

        return MediaInfo(
            path=path,
            duration=duration,
            video_codec=video_codec,
            audio_codec=audio_codec,
            container=container,
            resolution=(width, height),
            bitrate=bitrate,
            subtitle_tracks=subtitle_tracks,
            mime_type=mime_type,
        )

    @staticmethod
    def needs_transcode(
        media_info: MediaInfo,
        safe_codecs: tuple[set[str], set[str], set[str]] | None = None,
    ) -> bool:
        """Check whether the file needs transcoding for DLNA compatibility."""
        if safe_codecs:
            safe_v, safe_a, safe_c = safe_codecs
        else:
            safe_v, safe_a, safe_c = SAFE_VIDEO_CODECS, SAFE_AUDIO_CODECS, SAFE_CONTAINERS

        if media_info.video_codec and media_info.video_codec not in safe_v:
            return True

        if media_info.audio_codec and media_info.audio_codec not in safe_a:
            return True

        container = media_info.container
        if container and not any(c in container for c in safe_c):
            return True

        return False

    async def transcode_to_file(
        self,
        input_path: Path,
        output_path: Path,
        video_codec: str = "libx264",
        audio_codec: str = "aac",
    ) -> Path:
        """Transcode a media file to a DLNA-compatible format."""
        input_path = Path(input_path)
        output_path = Path(output_path)

        cmd = [
            "ffmpeg", "-y", "-i", str(input_path),
            "-vcodec", video_codec,
            "-acodec", audio_codec,
            "-movflags", "+faststart",
            str(output_path),
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
        except FileNotFoundError:
            raise TranscodeError("FFmpeg not found") from None

        if proc.returncode != 0:
            raise TranscodeError(
                f"Transcode failed (exit {proc.returncode}): "
                f"{stderr.decode(errors='replace').strip()[:500]}"
            )

        return output_path

    async def transcode_stream(
        self,
        input_path: Path,
        video_codec: str = "libx264",
        audio_codec: str = "aac",
        chunk_size: int = 65536,
    ) -> AsyncIterator[bytes]:
        """Stream transcode output as MPEG-TS byte chunks."""
        input_path = Path(input_path)

        cmd = [
            "ffmpeg", "-i", str(input_path),
            "-vcodec", video_codec,
            "-acodec", audio_codec,
            "-f", "mpegts",
            "pipe:1",
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            raise TranscodeError("FFmpeg not found") from None

        try:
            while True:
                chunk = await proc.stdout.read(chunk_size)
                if not chunk:
                    break
                yield chunk
        finally:
            if proc.returncode is None:
                proc.kill()
            await proc.wait()

    @staticmethod
    async def detect_hw_accel() -> list[str]:
        """Detect available hardware-accelerated H.264 encoders."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-hide_banner", "-encoders",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
        except FileNotFoundError:
            return []

        output = stdout.decode(errors="replace")
        found = []
        for encoder in HW_ENCODERS:
            if encoder in output:
                found.append(encoder)
        return found
