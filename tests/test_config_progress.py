"""Tests for playback progress persistence (断点续播)."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest import mock

import pytest

from lancaster import config


@pytest.fixture
def progress_dir():
    """Provide a temporary directory for progress file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        progress_file = tmpdir_path / "playback_progress.json"
        with (
            mock.patch.object(config, "_PROGRESS_FILE", progress_file),
            mock.patch.object(config, "_CONFIG_DIR", tmpdir_path),
        ):
            yield tmpdir_path


class TestSavePlaybackPosition:
    def test_saves_position(self, progress_dir):
        config.save_playback_position(
            "http://example.com/video.mp4", 120, 3600, "Test Video"
        )
        pos = config.get_playback_position("http://example.com/video.mp4")
        assert pos is not None
        assert pos["position"] == 120
        assert pos["duration"] == 3600
        assert pos["title"] == "Test Video"
        assert "ts" in pos

    def test_skips_if_position_too_small(self, progress_dir):
        config.save_playback_position(
            "http://example.com/video.mp4", 3, 3600, "Test"
        )
        assert config.get_playback_position("http://example.com/video.mp4") is None

    def test_removes_if_near_end(self, progress_dir):
        config.save_playback_position(
            "http://example.com/video.mp4", 100, 3600, "Test"
        )
        config.save_playback_position(
            "http://example.com/video.mp4", 3597, 3600, "Test"
        )
        assert config.get_playback_position("http://example.com/video.mp4") is None

    def test_skips_zero_duration(self, progress_dir):
        config.save_playback_position(
            "http://example.com/video.mp4", 100, 0, "Test"
        )
        assert config.get_playback_position("http://example.com/video.mp4") is None

    def test_updates_existing(self, progress_dir):
        config.save_playback_position(
            "/path/to/movie.mkv", 60, 7200, "Movie"
        )
        config.save_playback_position(
            "/path/to/movie.mkv", 300, 7200, "Movie"
        )
        pos = config.get_playback_position("/path/to/movie.mkv")
        assert pos["position"] == 300


class TestGetPlaybackPosition:
    def test_returns_none_for_unknown(self, progress_dir):
        assert config.get_playback_position("unknown") is None

    def test_returns_saved_data(self, progress_dir):
        config.save_playback_position(
            "test_file.mp4", 500, 2000, "Test"
        )
        result = config.get_playback_position("test_file.mp4")
        assert result["position"] == 500
        assert result["duration"] == 2000


class TestRemovePlaybackPosition:
    def test_removes_existing(self, progress_dir):
        config.save_playback_position("x.mp4", 100, 1000, "X")
        config.remove_playback_position("x.mp4")
        assert config.get_playback_position("x.mp4") is None

    def test_remove_nonexistent_no_error(self, progress_dir):
        config.remove_playback_position("nonexistent.mp4")


class TestMaxEntries:
    def test_evicts_oldest_when_over_limit(self, progress_dir):
        with mock.patch.object(config, "_MAX_PROGRESS_ENTRIES", 3):
            for i in range(5):
                config.save_playback_position(
                    f"video_{i}.mp4", 100, 1000, f"Video {i}"
                )

            data = config._load_progress()
            assert len(data) <= 3
            assert "video_4.mp4" in data
