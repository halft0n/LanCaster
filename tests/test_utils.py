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


def test_guess_mime_type_case_insensitive():
    assert guess_mime_type("VIDEO.MP4") == "video/mp4"
    assert guess_mime_type("audio.FLAC") == "audio/flac"


def test_guess_mime_type_various_video():
    assert guess_mime_type("v.avi") == "video/x-msvideo"
    assert guess_mime_type("v.mov") == "video/quicktime"
    assert guess_mime_type("v.wmv") == "video/x-ms-wmv"
    assert guess_mime_type("v.webm") == "video/webm"
    assert guess_mime_type("v.flv") == "video/x-flv"
    assert guess_mime_type("v.ts") == "video/mp2t"


def test_guess_mime_type_various_audio():
    assert guess_mime_type("a.wav") == "audio/wav"
    assert guess_mime_type("a.aac") == "audio/aac"
    assert guess_mime_type("a.ogg") == "audio/ogg"
    assert guess_mime_type("a.wma") == "audio/x-ms-wma"


def test_format_duration_zero():
    assert format_duration(timedelta(0)) == "00:00:00"


def test_parse_duration_zero():
    td = parse_duration("0")
    assert td == timedelta(0)


def test_parse_duration_large():
    td = parse_duration("99:59:59")
    assert td == timedelta(hours=99, minutes=59, seconds=59)


def test_list_local_ips_returns_list():
    from lancaster.utils import list_local_ips

    result = list_local_ips()
    assert isinstance(result, list)
    for ip in result:
        assert not ip.startswith("127.")


def test_list_local_ips_no_duplicates():
    from lancaster.utils import list_local_ips

    result = list_local_ips()
    assert len(result) == len(set(result))
