"""Tests for the DesktopMirror module (TDD — tests first)."""

from __future__ import annotations

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lancaster.mirror import DesktopMirror, QualityPreset
from lancaster.models import DeviceType, DLNADevice


def _make_device(name="Test TV"):
    return DLNADevice(
        name=name, ip="192.168.1.100",
        location="http://192.168.1.100:49152/description.xml",
        device_type=DeviceType.RENDERER,
    )


@pytest.fixture
def mock_http_server():
    srv = MagicMock()
    srv.serve_stream = AsyncMock(return_value="http://192.168.1.50:8201/stream/mirror")
    srv.host = "192.168.1.50"
    srv.port = 8201
    return srv


@pytest.fixture
def mock_controller():
    ctrl = MagicMock()
    ctrl.play_url = AsyncMock()
    ctrl.stop = AsyncMock()
    return ctrl


@pytest.fixture
def mirror(mock_http_server, mock_controller):
    return DesktopMirror(
        http_server=mock_http_server,
        controller=mock_controller,
    )


class TestQualityPreset:
    def test_low_preset(self):
        p = QualityPreset.from_name("low")
        assert p.bitrate_kbps == 2000
        assert p.scale_factor == 0.5

    def test_medium_preset(self):
        p = QualityPreset.from_name("medium")
        assert p.bitrate_kbps == 5000
        assert p.scale_factor == 1.0

    def test_high_preset(self):
        p = QualityPreset.from_name("high")
        assert p.bitrate_kbps == 10000
        assert p.scale_factor == 1.0

    def test_unknown_defaults_to_medium(self):
        p = QualityPreset.from_name("unknown")
        assert p.bitrate_kbps == 5000


class TestBuildCommand:
    def test_linux_command(self, mirror):
        """Linux should use x11grab."""
        with patch.object(sys, "platform", "linux"):
            cmd = mirror._build_ffmpeg_cmd(fps=30, quality="medium", audio=False)
        assert "x11grab" in cmd
        assert "pipe:1" in cmd
        assert "mpegts" in cmd

    def test_windows_command(self, mirror):
        """Windows should use gdigrab."""
        with patch.object(sys, "platform", "win32"):
            cmd = mirror._build_ffmpeg_cmd(fps=30, quality="medium", audio=False)
        assert "gdigrab" in cmd
        assert "desktop" in cmd

    def test_macos_command(self, mirror):
        """macOS should use avfoundation."""
        with patch.object(sys, "platform", "darwin"):
            cmd = mirror._build_ffmpeg_cmd(fps=25, quality="low", audio=False)
        assert "avfoundation" in cmd

    def test_fps_in_command(self, mirror):
        with patch.object(sys, "platform", "linux"):
            cmd = mirror._build_ffmpeg_cmd(fps=15, quality="medium", audio=False)
        assert "-framerate" in cmd
        idx = cmd.index("-framerate")
        assert cmd[idx + 1] == "15"

    def test_bitrate_from_quality(self, mirror):
        with patch.object(sys, "platform", "linux"):
            cmd = mirror._build_ffmpeg_cmd(fps=30, quality="high", audio=False)
        assert "-b:v" in cmd
        idx = cmd.index("-b:v")
        assert "10000k" in cmd[idx + 1]

    def test_scale_for_low_quality(self, mirror):
        with patch.object(sys, "platform", "linux"):
            cmd = mirror._build_ffmpeg_cmd(fps=30, quality="low", audio=False)
        cmd_str = " ".join(cmd)
        assert "scale" in cmd_str


class TestMirrorLifecycle:
    @pytest.mark.asyncio
    async def test_start_and_stop(self, mirror, mock_controller):
        """Start should launch FFmpeg and cast; stop should kill process."""
        device = _make_device()

        mock_proc = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.pid = 12345
        mock_proc.returncode = None
        mock_proc.kill = MagicMock()
        mock_proc.wait = AsyncMock()

        async def fake_read(n):
            await asyncio.sleep(0.01)
            return b"\x47" * 188

        mock_proc.stdout.read = fake_read

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            await mirror.start(device, fps=30, quality="medium")

        assert mirror.is_running

        await mirror.stop()
        mock_proc.kill.assert_called_once()
        assert not mirror.is_running

    @pytest.mark.asyncio
    async def test_not_running_initially(self, mirror):
        assert not mirror.is_running

    @pytest.mark.asyncio
    async def test_double_start_raises(self, mirror):
        """Starting mirror twice should raise."""
        device = _make_device()

        mock_proc = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.pid = 12345
        mock_proc.returncode = None
        mock_proc.kill = MagicMock()
        mock_proc.wait = AsyncMock()
        mock_proc.stdout.read = AsyncMock(return_value=b"\x47" * 188)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            await mirror.start(device, fps=30, quality="medium")
            with pytest.raises(RuntimeError, match="already running"):
                await mirror.start(device, fps=30, quality="medium")

        await mirror.stop()

    @pytest.mark.asyncio
    async def test_stop_when_not_running(self, mirror):
        """Stop on inactive mirror should be a no-op."""
        await mirror.stop()

    @pytest.mark.asyncio
    async def test_ffmpeg_not_found(self, mirror):
        device = _make_device()
        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError("ffmpeg not found"),
        ):
            with pytest.raises(RuntimeError, match="FFmpeg|not found"):
                await mirror.start(device, fps=30, quality="medium")
