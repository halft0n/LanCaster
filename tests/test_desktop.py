"""Tests for the LanCaster desktop GUI module."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

from lancaster.desktop import DesktopApp, _DesktopBridge

# === DesktopApp ===


class TestDesktopApp:
    def test_default_port(self):
        app = DesktopApp()
        assert app._port == 8200

    def test_custom_port(self):
        app = DesktopApp(port=9000)
        assert app._port == 9000

    def test_custom_host(self):
        app = DesktopApp(host="192.168.1.50")
        assert app._host == "192.168.1.50"

    def test_initial_state(self):
        app = DesktopApp()
        assert app._web_server is None
        assert app._window is None
        assert app._tray_icon is None
        assert app._loop is None
        assert app._server_thread is None

    def test_expose_api_returns_bridge(self):
        app = DesktopApp()
        bridge = app._expose_api()
        assert isinstance(bridge, _DesktopBridge)
        assert bridge._app is app

    def test_show_window_with_no_window(self):
        app = DesktopApp()
        app._show_window()

    def test_show_window_calls_show_and_restore(self):
        app = DesktopApp()
        mock_win = MagicMock()
        app._window = mock_win
        app._show_window()
        mock_win.show.assert_called_once()
        mock_win.restore.assert_called_once()

    def test_quit_destroys_window(self):
        app = DesktopApp()
        mock_win = MagicMock()
        app._window = mock_win
        app._loop = None
        app._quit()
        mock_win.destroy.assert_called_once()

    def test_quit_stops_server(self):
        app = DesktopApp()
        mock_loop = MagicMock()
        mock_task = MagicMock()
        app._loop = mock_loop
        app._server_task = mock_task
        app._window = None
        app._quit()
        mock_loop.call_soon_threadsafe.assert_called_once_with(mock_task.cancel)

    def test_stop_server_noop_when_no_loop(self):
        app = DesktopApp()
        app._loop = None
        app._stop_server()


# === DesktopBridge ===


class TestDesktopBridge:
    def _make_bridge(self):
        app = DesktopApp()
        return _DesktopBridge(app)

    def test_cast_empty_files(self):
        bridge = self._make_bridge()
        result = bridge.cast_dropped_files([])
        assert result["ok"] is False
        assert "error" in result

    def test_cast_single_video(self):
        bridge = self._make_bridge()
        result = bridge.cast_dropped_files(["/home/user/movie.mp4"])
        assert result["ok"] is True
        assert result["video"] == "/home/user/movie.mp4"
        assert result["subtitle"] is None

    def test_cast_video_with_subtitle(self):
        bridge = self._make_bridge()
        result = bridge.cast_dropped_files(
            [
                "/home/user/movie.mkv",
                "/home/user/movie.srt",
            ]
        )
        assert result["ok"] is True
        assert result["video"] == "/home/user/movie.mkv"
        assert result["subtitle"] == "/home/user/movie.srt"

    def test_cast_subtitle_only_fallback(self):
        bridge = self._make_bridge()
        result = bridge.cast_dropped_files(["/home/user/sub.srt"])
        assert result["ok"] is True
        assert result["video"] == "/home/user/sub.srt"

    def test_cast_unknown_ext_fallback(self):
        bridge = self._make_bridge()
        result = bridge.cast_dropped_files(["/home/user/data.xyz"])
        assert result["ok"] is True
        assert result["video"] == "/home/user/data.xyz"

    def test_cast_multiple_videos_picks_last(self):
        bridge = self._make_bridge()
        result = bridge.cast_dropped_files(
            [
                "/home/user/a.mp4",
                "/home/user/b.mkv",
            ]
        )
        assert result["ok"] is True
        assert result["video"] == "/home/user/b.mkv"

    def test_cast_audio_file(self):
        bridge = self._make_bridge()
        result = bridge.cast_dropped_files(["/home/user/song.mp3"])
        assert result["ok"] is True
        assert result["video"] == "/home/user/song.mp3"

    def test_cast_ass_subtitle(self):
        bridge = self._make_bridge()
        result = bridge.cast_dropped_files(
            [
                "/home/user/movie.mp4",
                "/home/user/movie.ass",
            ]
        )
        assert result["subtitle"] == "/home/user/movie.ass"

    def test_cast_vtt_subtitle(self):
        bridge = self._make_bridge()
        result = bridge.cast_dropped_files(
            [
                "/home/user/movie.avi",
                "/home/user/movie.vtt",
            ]
        )
        assert result["subtitle"] == "/home/user/movie.vtt"

    def test_get_platform(self):
        bridge = self._make_bridge()
        assert bridge.get_platform() == sys.platform

    def test_minimize_to_tray_no_window(self):
        bridge = self._make_bridge()
        bridge.minimize_to_tray()

    def test_minimize_to_tray_hides_window(self):
        bridge = self._make_bridge()
        mock_win = MagicMock()
        bridge._app._window = mock_win
        bridge.minimize_to_tray()
        mock_win.hide.assert_called_once()


# === Tray icon ===


class TestTrayIcon:
    def test_tray_icon_missing_deps(self):
        from lancaster.desktop import _create_tray_icon

        with patch.dict("sys.modules", {"pystray": None}):
            result = _create_tray_icon(lambda: None, lambda: None)
            assert result is None
