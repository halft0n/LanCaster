"""Tests for the Transcoder module (TDD — written before implementation)."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lancaster.exceptions import TranscodeError
from lancaster.models import MediaInfo
from lancaster.transcoder import Transcoder

# === Fixtures ===


@pytest.fixture
def ffprobe_mp4_output():
    """Simulated ffprobe JSON output for an H.264/AAC MP4 file."""
    return """{
  "streams": [
    {
      "codec_type": "video",
      "codec_name": "h264",
      "width": 1920,
      "height": 1080,
      "bit_rate": "5000000",
      "duration": "7200.0"
    },
    {
      "codec_type": "audio",
      "codec_name": "aac",
      "channels": 2,
      "bit_rate": "128000"
    }
  ],
  "format": {
    "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
    "duration": "7200.000000",
    "bit_rate": "5128000"
  }
}"""


@pytest.fixture
def ffprobe_mkv_hevc_output():
    """Simulated ffprobe JSON output for an HEVC/DTS MKV file."""
    return """{
  "streams": [
    {
      "codec_type": "video",
      "codec_name": "hevc",
      "width": 3840,
      "height": 2160,
      "bit_rate": "15000000",
      "duration": "5400.0"
    },
    {
      "codec_type": "audio",
      "codec_name": "dts",
      "channels": 6,
      "bit_rate": "1509000"
    },
    {
      "codec_type": "subtitle",
      "codec_name": "subrip"
    }
  ],
  "format": {
    "format_name": "matroska,webm",
    "duration": "5400.000000",
    "bit_rate": "16509000"
  }
}"""


# === Probe Tests ===


class TestProbe:
    @pytest.mark.asyncio
    async def test_probe_mp4(self, tmp_path, ffprobe_mp4_output):
        """ffprobe should return valid MediaInfo for H.264/AAC MP4."""
        fake_file = tmp_path / "test.mp4"
        fake_file.write_bytes(b"\x00" * 100)

        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(
            return_value=(ffprobe_mp4_output.encode(), b""),
        )
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            info = await Transcoder.probe(fake_file)

        assert isinstance(info, MediaInfo)
        assert info.video_codec == "h264"
        assert info.audio_codec == "aac"
        assert info.resolution == (1920, 1080)
        assert info.duration == timedelta(seconds=7200)
        assert "mp4" in info.container

    @pytest.mark.asyncio
    async def test_probe_mkv_hevc(self, tmp_path, ffprobe_mkv_hevc_output):
        """ffprobe should parse HEVC/DTS/MKV with subtitle tracks."""
        fake_file = tmp_path / "test.mkv"
        fake_file.write_bytes(b"\x00" * 100)

        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(
            return_value=(ffprobe_mkv_hevc_output.encode(), b""),
        )
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            info = await Transcoder.probe(fake_file)

        assert info.video_codec == "hevc"
        assert info.audio_codec == "dts"
        assert info.resolution == (3840, 2160)
        assert "matroska" in info.container
        assert len(info.subtitle_tracks) == 1

    @pytest.mark.asyncio
    async def test_probe_nonexistent_raises(self):
        """Probing a nonexistent file should raise TranscodeError."""
        with pytest.raises(TranscodeError, match="not found|not exist|No such"):
            await Transcoder.probe(Path("/nonexistent/file.mp4"))

    @pytest.mark.asyncio
    async def test_probe_ffprobe_missing(self, tmp_path):
        """Missing ffprobe binary should raise TranscodeError."""
        fake_file = tmp_path / "test.mp4"
        fake_file.write_bytes(b"\x00" * 100)

        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError("ffprobe not found"),
        ):
            with pytest.raises(TranscodeError, match="ffprobe|FFmpeg|not found"):
                await Transcoder.probe(fake_file)

    @pytest.mark.asyncio
    async def test_probe_ffprobe_failure(self, tmp_path):
        """ffprobe returning non-zero should raise TranscodeError."""
        fake_file = tmp_path / "test.mp4"
        fake_file.write_bytes(b"\x00" * 100)

        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(
            return_value=(b"", b"Invalid data found"),
        )
        mock_proc.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with pytest.raises(TranscodeError):
                await Transcoder.probe(fake_file)


# === NeedsTranscode Tests ===


class TestNeedsTranscode:
    def test_h264_aac_mp4_no_transcode(self):
        """H.264 + AAC + MP4 = universal, no transcode needed."""
        info = MediaInfo(
            path="/test.mp4",
            video_codec="h264",
            audio_codec="aac",
            container="mp4",
        )
        assert not Transcoder.needs_transcode(info)

    def test_h264_aac_mov_no_transcode(self):
        """MOV container with H.264 should not need transcode."""
        info = MediaInfo(
            path="/test.mov",
            video_codec="h264",
            audio_codec="aac",
            container="mov,mp4,m4a,3gp,3g2,mj2",
        )
        assert not Transcoder.needs_transcode(info)

    def test_hevc_needs_transcode(self):
        """HEVC video codec needs transcode for most TVs."""
        info = MediaInfo(
            path="/test.mkv",
            video_codec="hevc",
            audio_codec="aac",
            container="matroska",
        )
        assert Transcoder.needs_transcode(info)

    def test_vp9_needs_transcode(self):
        """VP9 needs transcode."""
        info = MediaInfo(
            path="/test.webm",
            video_codec="vp9",
            audio_codec="opus",
            container="webm",
        )
        assert Transcoder.needs_transcode(info)

    def test_dts_audio_needs_transcode(self):
        """DTS audio needs transcode even with H.264 video."""
        info = MediaInfo(
            path="/test.mp4",
            video_codec="h264",
            audio_codec="dts",
            container="mp4",
        )
        assert Transcoder.needs_transcode(info)

    def test_ac3_audio_no_transcode(self):
        """AC3 audio is commonly supported, no transcode."""
        info = MediaInfo(
            path="/test.mp4",
            video_codec="h264",
            audio_codec="ac3",
            container="mp4",
        )
        assert not Transcoder.needs_transcode(info)

    def test_mkv_container_needs_transcode(self):
        """MKV container may need transcode (some TVs don't support)."""
        info = MediaInfo(
            path="/test.mkv",
            video_codec="h264",
            audio_codec="aac",
            container="matroska",
        )
        assert Transcoder.needs_transcode(info)

    def test_custom_safe_codecs(self):
        """Custom safe codec set should be respected."""
        info = MediaInfo(
            path="/test.mkv",
            video_codec="hevc",
            audio_codec="aac",
            container="matroska",
        )
        safe = {"hevc"}, {"aac"}, {"matroska"}
        assert not Transcoder.needs_transcode(info, safe_codecs=safe)

    def test_audio_only(self):
        """Audio-only file with supported codec should not transcode."""
        info = MediaInfo(
            path="/test.mp3",
            video_codec="",
            audio_codec="mp3",
            container="mp3",
        )
        assert not Transcoder.needs_transcode(info)


# === HW Accel Detection ===


class TestHWAccel:
    @pytest.mark.asyncio
    async def test_detect_hw_accel(self):
        """Should return a list of available encoders."""
        ffmpeg_output = b"""Encoders:
 V..... h264_nvenc
 V..... h264_qsv
 V..... libx264"""

        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(return_value=(ffmpeg_output, b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            accels = await Transcoder.detect_hw_accel()

        assert "h264_nvenc" in accels
        assert "h264_qsv" in accels

    @pytest.mark.asyncio
    async def test_detect_hw_accel_no_ffmpeg(self):
        """Missing FFmpeg should return empty list."""
        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError(),
        ):
            accels = await Transcoder.detect_hw_accel()
        assert accels == []


# === Transcode to File ===


class TestTranscodeToFile:
    @pytest.mark.asyncio
    async def test_transcode_creates_output(self, tmp_path):
        """Transcode should produce an output file."""
        input_file = tmp_path / "input.mkv"
        input_file.write_bytes(b"\x00" * 100)
        output_file = tmp_path / "output.mp4"

        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            t = Transcoder()
            output_file.write_bytes(b"\x00" * 50)
            result = await t.transcode_to_file(input_file, output_file)

        assert result == output_file

    @pytest.mark.asyncio
    async def test_transcode_failure_raises(self, tmp_path):
        """FFmpeg failure should raise TranscodeError."""
        input_file = tmp_path / "input.mkv"
        input_file.write_bytes(b"\x00" * 100)

        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(
            return_value=(b"", b"Conversion failed"),
        )
        mock_proc.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            t = Transcoder()
            with pytest.raises(TranscodeError, match="failed|error"):
                await t.transcode_to_file(
                    input_file,
                    tmp_path / "output.mp4",
                )


# === Transcode Stream ===


class TestTranscodeStream:
    @pytest.mark.asyncio
    async def test_stream_produces_bytes(self, tmp_path):
        """Streaming transcode should yield byte chunks."""
        input_file = tmp_path / "input.mkv"
        input_file.write_bytes(b"\x00" * 100)

        mock_proc = MagicMock()
        mock_proc.stdout = MagicMock()

        async def fake_read(n):
            fake_read.call_count = getattr(fake_read, "call_count", 0) + 1
            if fake_read.call_count <= 3:
                return b"\x47" * 188
            return b""

        mock_proc.stdout.read = fake_read
        mock_proc.wait = AsyncMock(return_value=0)
        mock_proc.kill = MagicMock()
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            t = Transcoder()
            chunks = []
            async for chunk in t.transcode_stream(input_file):
                chunks.append(chunk)

        assert len(chunks) == 3
        assert all(len(c) == 188 for c in chunks)
