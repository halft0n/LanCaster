"""Tests for data models."""

from datetime import timedelta

from lancaster.models import DeviceType, DLNADevice, MediaInfo, PlaybackInfo, TransportState


def test_dlna_device_str():
    dev = DLNADevice(
        name="Living Room TV",
        ip="192.168.1.10",
        location="http://192.168.1.10:49152/desc.xml",
        device_type=DeviceType.RENDERER,
    )
    assert "Living Room TV" in str(dev)
    assert "192.168.1.10" in str(dev)
    assert "renderer" in str(dev)


def test_device_type_values():
    assert DeviceType.RENDERER.value == "renderer"
    assert DeviceType.SERVER.value == "server"


def test_transport_state_values():
    assert TransportState.PLAYING.value == "PLAYING"
    assert TransportState.PAUSED.value == "PAUSED_PLAYBACK"
    assert TransportState.STOPPED.value == "STOPPED"


def test_media_info_defaults():
    info = MediaInfo(path="/tmp/test.mp4")
    assert info.duration == timedelta()
    assert info.video_codec == ""
    assert info.resolution == (0, 0)
    assert info.mime_type == "video/mp4"


def test_playback_info_defaults():
    info = PlaybackInfo()
    assert info.state == TransportState.STOPPED
    assert info.position == timedelta()
    assert info.volume == 0
