"""Tests for DIDL-Lite builder."""

from datetime import timedelta

from lancaster.didl import DIDLBuilder


def test_video_item_basic():
    xml = DIDLBuilder.video_item(
        url="http://192.168.1.5:8200/file/abc123",
        title="Test Video",
        mime="video/mp4",
    )
    assert "<DIDL-Lite" in xml
    assert "Test Video" in xml
    assert "http://192.168.1.5:8200/file/abc123" in xml
    assert "video/mp4" in xml
    assert "object.item.videoItem" in xml


def test_video_item_with_duration():
    xml = DIDLBuilder.video_item(
        url="http://example.com/video.mp4",
        title="Timed Video",
        mime="video/mp4",
        duration=timedelta(hours=1, minutes=30),
    )
    assert 'duration="01:30:00"' in xml


def test_video_item_with_subtitle():
    xml = DIDLBuilder.video_item(
        url="http://example.com/video.mp4",
        title="Subbed Video",
        mime="video/mp4",
        subtitle_url="http://example.com/sub.srt",
    )
    assert "CaptionInfoEx" in xml
    assert "http://example.com/sub.srt" in xml


def test_audio_item():
    xml = DIDLBuilder.audio_item(
        url="http://example.com/song.mp3",
        title="Test Song",
        mime="audio/mpeg",
        artist="Artist",
        album="Album",
    )
    assert "Test Song" in xml
    assert "Artist" in xml
    assert "Album" in xml
    assert "musicTrack" in xml


def test_container():
    xml = DIDLBuilder.container(
        container_id="1",
        title="Movies",
        child_count=42,
    )
    assert "Movies" in xml
    assert 'childCount="42"' in xml
    assert "storageFolder" in xml


def test_xml_escaping():
    xml = DIDLBuilder.video_item(
        url="http://example.com/video.mp4?a=1&b=2",
        title='Movie "Title" <Special>',
        mime="video/mp4",
    )
    assert "&amp;" in xml
    assert "&lt;" in xml
    assert "&gt;" in xml
