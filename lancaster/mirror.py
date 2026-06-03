"""Desktop mirroring via FFmpeg screen capture to DLNA renderer."""

from __future__ import annotations

import asyncio
import logging
import sys
from dataclasses import dataclass

from lancaster.controller import MediaController
from lancaster.http_server import HTTPFileServer
from lancaster.models import DLNADevice

_LOGGER = logging.getLogger(__name__)


@dataclass
class QualityPreset:
    bitrate_kbps: int
    scale_factor: float
    preset: str

    @staticmethod
    def from_name(name: str) -> QualityPreset:
        presets = {
            "low": QualityPreset(bitrate_kbps=2000, scale_factor=0.5, preset="ultrafast"),
            "medium": QualityPreset(bitrate_kbps=5000, scale_factor=1.0, preset="ultrafast"),
            "high": QualityPreset(bitrate_kbps=10000, scale_factor=1.0, preset="fast"),
        }
        return presets.get(name, presets["medium"])


class DesktopMirror:
    """Stream the desktop screen to a DLNA renderer via FFmpeg."""

    def __init__(
        self,
        http_server: HTTPFileServer,
        controller: MediaController,
    ) -> None:
        self._http_server = http_server
        self._controller = controller
        self._process: asyncio.subprocess.Process | None = None
        self._stream_task: asyncio.Task | None = None
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    def _build_ffmpeg_cmd(
        self,
        fps: int = 30,
        quality: str = "medium",
        audio: bool = False,
    ) -> list[str]:
        """Build FFmpeg command for screen capture based on OS."""
        preset = QualityPreset.from_name(quality)
        bitrate = f"{preset.bitrate_kbps}k"
        bufsize = f"{preset.bitrate_kbps * 2}k"

        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error"]

        if sys.platform == "win32":
            cmd.extend(["-f", "gdigrab", "-framerate", str(fps), "-i", "desktop"])
        elif sys.platform == "darwin":
            cmd.extend(["-f", "avfoundation", "-framerate", str(fps), "-i", "1:none"])
        else:
            display = ":0.0"
            cmd.extend(["-f", "x11grab", "-framerate", str(fps), "-i", display])

        vf_filters = []
        if preset.scale_factor < 1.0:
            w = f"iw*{preset.scale_factor}"
            h = f"ih*{preset.scale_factor}"
            vf_filters.append(f"scale={w}:{h}")

        cmd.extend(
            [
                "-vcodec",
                "libx264",
                "-preset",
                preset.preset,
                "-tune",
                "zerolatency",
                "-pix_fmt",
                "yuv420p",
                "-g",
                str(fps * 2),
                "-b:v",
                bitrate,
                "-maxrate",
                bitrate,
                "-bufsize",
                bufsize,
            ]
        )

        if vf_filters:
            cmd.extend(["-vf", ",".join(vf_filters)])

        if not audio:
            cmd.extend(["-an"])

        cmd.extend(["-f", "mpegts", "pipe:1"])
        return cmd

    async def start(
        self,
        device: DLNADevice,
        fps: int = 30,
        quality: str = "medium",
        audio: bool = False,
    ) -> None:
        """Start desktop mirroring to the given device."""
        if self._running:
            raise RuntimeError("Mirror is already running")

        cmd = self._build_ffmpeg_cmd(fps=fps, quality=quality, audio=audio)
        _LOGGER.info("Starting mirror: %s", " ".join(cmd))

        try:
            self._process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            raise RuntimeError(
                "FFmpeg not found. Please install FFmpeg for desktop mirroring."
            ) from None

        self._running = True

        stream_url = self._http_server.serve_stream(self._process.stdout)

        await self._controller.play_url(
            device,
            stream_url,
            title="LanCaster Desktop Mirror",
        )

    async def stop(self) -> None:
        """Stop desktop mirroring and kill FFmpeg process."""
        if not self._running:
            return

        if self._process and self._process.returncode is None:
            self._process.kill()
            await self._process.wait()

        self._running = False
        self._process = None
        _LOGGER.info("Desktop mirror stopped")
