"""Tests for utility functions."""

from datetime import timedelta

from lancaster.utils import format_duration, get_local_ip, guess_mime_type, parse_duration


def test_get_local_ip():
    ip = get_local_ip()
    assert ip != ""
    parts = ip.split(".")
    assert len(parts) == 4


def test_guess_mime_type_known():
    assert guess_mime_type("video.mp4") == "video/mp4"
    assert guess_mime_type("video.mkv") == "video/x-matroska"
    assert guess_mime_type("audio.mp3") == "audio/mpeg"
    assert guess_mime_type("sub.srt") == "text/srt"


def test_guess_mime_type_unknown():
    result = guess_mime_type("file.xyz123")
    assert result == "application/octet-stream"


def test_format_duration():
    assert format_duration(timedelta(hours=1, minutes=23, seconds=45)) == "01:23:45"
    assert format_duration(timedelta(seconds=5)) == "00:00:05"
    assert format_duration(timedelta(hours=10)) == "10:00:00"


def test_parse_duration_hhmmss():
    td = parse_duration("01:23:45")
    assert td == timedelta(hours=1, minutes=23, seconds=45)


def test_parse_duration_mmss():
    td = parse_duration("5:30")
    assert td == timedelta(minutes=5, seconds=30)


def test_parse_duration_seconds():
    td = parse_duration("90")
    assert td == timedelta(seconds=90)
