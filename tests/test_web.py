"""Tests for the LanCaster Web UI server."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lancaster.models import (
    DeviceType,
    DLNADevice,
    PlaybackInfo,
    TransportState,
)
from lancaster.web import WebServer


def _make_device(name="Test TV", ip="192.168.1.100", dtype=DeviceType.RENDERER):
    return DLNADevice(
        name=name,
        ip=ip,
        location=f"http://{ip}:49152/description.xml",
        device_type=dtype,
        manufacturer="TestCorp",
        model="Model-X",
        udn=f"uuid:{name.lower().replace(' ', '-')}",
    )


@pytest.fixture
def web_server():
    """Create a WebServer with mocked internal services."""
    with (
        patch("lancaster.web.HTTPFileServer") as mock_http,
        patch("lancaster.web.DeviceDiscovery") as mock_disc,
        patch("lancaster.web.MediaController") as mock_ctrl,
    ):
        mock_http_inst = MagicMock()
        mock_http_inst.start = AsyncMock()
        mock_http_inst.stop = AsyncMock()
        mock_http.return_value = mock_http_inst

        mock_disc_inst = MagicMock()
        mock_disc_inst.scan = AsyncMock(return_value=[])
        mock_disc_inst.renderers = []
        mock_disc_inst.stop_watch = AsyncMock()
        mock_disc_inst.find_by_name = MagicMock(return_value=None)
        mock_disc.return_value = mock_disc_inst

        mock_ctrl_inst = MagicMock()
        mock_ctrl_inst.play_url = AsyncMock()
        mock_ctrl_inst.play_file = AsyncMock()
        mock_ctrl_inst.pause = AsyncMock()
        mock_ctrl_inst.resume = AsyncMock()
        mock_ctrl_inst.stop = AsyncMock()
        mock_ctrl_inst.seek = AsyncMock()
        mock_ctrl_inst.set_volume = AsyncMock()
        mock_ctrl_inst.get_position = AsyncMock(return_value=PlaybackInfo())
        mock_ctrl.return_value = mock_ctrl_inst

        srv = WebServer(host="127.0.0.1", port=18200)

        yield {
            "server": srv,
            "app": srv._app,
            "discovery": mock_disc_inst,
            "controller": mock_ctrl_inst,
            "http_server": mock_http_inst,
        }


@pytest.fixture
def client(web_server, aiohttp_client):
    return aiohttp_client(web_server["app"])


# === Index Page ===


class TestIndexPage:
    @pytest.mark.asyncio
    async def test_index_returns_html(self, client):
        c = await client
        resp = await c.get("/")
        assert resp.status == 200
        text = await resp.text()
        assert "LanCaster" in text
        assert "alpine" in text.lower()


# === Device API ===


class TestDeviceAPI:
    @pytest.mark.asyncio
    async def test_scan_empty(self, client, web_server):
        web_server["discovery"].scan = AsyncMock(return_value=[])
        c = await client
        resp = await c.get("/api/devices?timeout=1")
        assert resp.status == 200
        data = await resp.json()
        assert data == []

    @pytest.mark.asyncio
    async def test_scan_finds_devices(self, client, web_server):
        devices = [_make_device("TV-1", "192.168.1.10"), _make_device("TV-2", "192.168.1.11")]
        web_server["discovery"].scan = AsyncMock(return_value=devices)
        web_server["discovery"].renderers = devices

        c = await client
        resp = await c.get("/api/devices?timeout=1")
        data = await resp.json()
        assert len(data) == 2
        assert data[0]["name"] == "TV-1"
        assert data[1]["ip"] == "192.168.1.11"

    @pytest.mark.asyncio
    async def test_select_device(self, client, web_server):
        c = await client
        resp = await c.post("/api/devices/select", json={"name": "TV-1"})
        data = await resp.json()
        assert data["ok"] is True
        assert data["selected"] == "TV-1"


# === Cast API ===


class TestCastAPI:
    @pytest.mark.asyncio
    async def test_cast_url(self, client, web_server):
        device = _make_device()
        web_server["discovery"].renderers = [device]
        web_server["discovery"].find_by_name = MagicMock(return_value=device)
        web_server["server"]._selected_device = device.name

        c = await client
        resp = await c.post("/api/cast", json={"target": "http://example.com/video.mp4"})
        data = await resp.json()
        assert data["ok"] is True
        web_server["controller"].play_url.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cast_file(self, client, web_server):
        device = _make_device()
        web_server["discovery"].renderers = [device]
        web_server["discovery"].find_by_name = MagicMock(return_value=device)
        web_server["server"]._selected_device = device.name

        c = await client
        resp = await c.post("/api/cast", json={"target": "/tmp/video.mp4"})
        data = await resp.json()
        assert data["ok"] is True
        web_server["controller"].play_file.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cast_no_device(self, client, web_server):
        web_server["discovery"].renderers = []
        c = await client
        resp = await c.post("/api/cast", json={"target": "http://example.com/v.mp4"})
        assert resp.status == 400
        data = await resp.json()
        assert "error" in data


# === Control API ===


class TestControlAPI:
    @pytest.mark.asyncio
    async def test_pause(self, client, web_server):
        device = _make_device()
        web_server["discovery"].renderers = [device]
        c = await client
        resp = await c.post("/api/control/pause")
        assert (await resp.json())["ok"] is True
        web_server["controller"].pause.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_resume(self, client, web_server):
        device = _make_device()
        web_server["discovery"].renderers = [device]
        c = await client
        resp = await c.post("/api/control/resume")
        assert (await resp.json())["ok"] is True

    @pytest.mark.asyncio
    async def test_stop(self, client, web_server):
        device = _make_device()
        web_server["discovery"].renderers = [device]
        c = await client
        resp = await c.post("/api/control/stop")
        assert (await resp.json())["ok"] is True

    @pytest.mark.asyncio
    async def test_seek(self, client, web_server):
        device = _make_device()
        web_server["discovery"].renderers = [device]
        c = await client
        resp = await c.post("/api/control/seek", json={"position": "00:05:30"})
        assert (await resp.json())["ok"] is True
        web_server["controller"].seek.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_volume(self, client, web_server):
        device = _make_device()
        web_server["discovery"].renderers = [device]
        c = await client
        resp = await c.post("/api/control/volume", json={"level": 75})
        assert (await resp.json())["ok"] is True
        web_server["controller"].set_volume.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_unknown_action(self, client, web_server):
        device = _make_device()
        web_server["discovery"].renderers = [device]
        c = await client
        resp = await c.post("/api/control/foobar")
        assert resp.status == 400


# === Status API ===


class TestStatusAPI:
    @pytest.mark.asyncio
    async def test_status_no_device(self, client, web_server):
        web_server["discovery"].renderers = []
        c = await client
        resp = await c.get("/api/status")
        data = await resp.json()
        assert data["state"] == "NO_DEVICE"
        assert data["device"] is None
        assert "queue_index" in data
        assert "queue_length" in data

    @pytest.mark.asyncio
    async def test_status_playing(self, client, web_server):
        device = _make_device()
        web_server["discovery"].renderers = [device]
        web_server["controller"].get_position = AsyncMock(
            return_value=PlaybackInfo(
                state=TransportState.PLAYING,
                position=timedelta(minutes=5, seconds=30),
                duration=timedelta(hours=1, minutes=30),
                volume=65,
                title="Test Movie",
            )
        )
        c = await client
        resp = await c.get("/api/status")
        data = await resp.json()
        assert data["state"] == "PLAYING"
        assert data["device"] == "Test TV"
        assert data["volume"] == 65


# === Queue API ===


class TestQueueAPI:
    @pytest.mark.asyncio
    async def test_queue_empty(self, client, web_server):
        c = await client
        resp = await c.get("/api/queue")
        data = await resp.json()
        assert data["items"] == []
        assert data["index"] == -1

    @pytest.mark.asyncio
    async def test_queue_add_and_get(self, client, web_server):
        c = await client
        resp = await c.post(
            "/api/queue/add",
            json={
                "targets": [
                    "http://example.com/a.mp4",
                    "/home/user/b.mkv",
                ]
            },
        )
        data = await resp.json()
        assert data["ok"] is True
        assert data["length"] == 2

        resp = await c.get("/api/queue")
        data = await resp.json()
        assert len(data["items"]) == 2
        assert data["items"][0]["is_url"] is True
        assert data["items"][1]["is_url"] is False

    @pytest.mark.asyncio
    async def test_queue_remove(self, client, web_server):
        c = await client
        await c.post("/api/queue/add", json={"targets": ["a.mp4", "b.mp4", "c.mp4"]})

        resp = await c.post("/api/queue/remove", json={"index": 1})
        data = await resp.json()
        assert data["ok"] is True
        assert data["length"] == 2

    @pytest.mark.asyncio
    async def test_queue_clear(self, client, web_server):
        c = await client
        await c.post("/api/queue/add", json={"targets": ["a.mp4", "b.mp4"]})

        resp = await c.post("/api/queue/clear")
        assert (await resp.json())["ok"] is True

        resp = await c.get("/api/queue")
        assert len((await resp.json())["items"]) == 0

    @pytest.mark.asyncio
    async def test_queue_play(self, client, web_server):
        device = _make_device()
        web_server["discovery"].renderers = [device]

        c = await client
        await c.post("/api/queue/add", json={"targets": ["/tmp/a.mp4", "/tmp/b.mp4"]})

        resp = await c.post("/api/queue/play", json={"index": 0})
        data = await resp.json()
        assert data["ok"] is True
        web_server["controller"].play_file.assert_awaited()

    @pytest.mark.asyncio
    async def test_queue_next_prev(self, client, web_server):
        device = _make_device()
        web_server["discovery"].renderers = [device]

        c = await client
        await c.post("/api/queue/add", json={"targets": ["/a.mp4", "/b.mp4", "/c.mp4"]})
        await c.post("/api/queue/play", json={"index": 0})

        resp = await c.post("/api/queue/next")
        assert (await resp.json())["ok"] is True

        resp = await c.post("/api/queue/prev")
        assert (await resp.json())["ok"] is True

    @pytest.mark.asyncio
    async def test_queue_next_at_end(self, client, web_server):
        device = _make_device()
        web_server["discovery"].renderers = [device]

        c = await client
        await c.post("/api/queue/add", json={"targets": ["/a.mp4"]})
        await c.post("/api/queue/play", json={"index": 0})

        resp = await c.post("/api/queue/next")
        assert resp.status == 400

    @pytest.mark.asyncio
    async def test_queue_reorder(self, client, web_server):
        c = await client
        await c.post("/api/queue/add", json={"targets": ["a.mp4", "b.mp4", "c.mp4"]})

        resp = await c.post("/api/queue/reorder", json={"from": 0, "to": 2})
        assert (await resp.json())["ok"] is True

        resp = await c.get("/api/queue")
        items = (await resp.json())["items"]
        assert items[0]["title"] == "b.mp4"
        assert items[2]["title"] == "a.mp4"

    @pytest.mark.asyncio
    async def test_queue_play_empty(self, client, web_server):
        c = await client
        resp = await c.post("/api/queue/play", json={"index": 0})
        assert resp.status == 400


# === Settings API ===


class TestSettingsAPI:
    @pytest.mark.asyncio
    async def test_get_defaults(self, client, web_server):
        c = await client
        resp = await c.get("/api/settings")
        data = await resp.json()
        assert data["poll_interval"] == 2.0
        assert data["auto_scan"] is False
        assert data["default_volume"] == 50

    @pytest.mark.asyncio
    async def test_update_settings(self, client, web_server):
        c = await client
        resp = await c.post(
            "/api/settings",
            json={
                "poll_interval": 3.0,
                "default_volume": 80,
            },
        )
        assert (await resp.json())["ok"] is True

        resp = await c.get("/api/settings")
        data = await resp.json()
        assert data["poll_interval"] == 3.0
        assert data["default_volume"] == 80

    @pytest.mark.asyncio
    async def test_poll_interval_minimum(self, client, web_server):
        c = await client
        await c.post("/api/settings", json={"poll_interval": 0.1})
        resp = await c.get("/api/settings")
        data = await resp.json()
        assert data["poll_interval"] >= 0.5


# === Mirror API ===


class TestMirrorAPI:
    @pytest.mark.asyncio
    async def test_mirror_status_initially_stopped(self, client, web_server):
        c = await client
        resp = await c.get("/api/mirror/status")
        data = await resp.json()
        assert data["running"] is False

    @pytest.mark.asyncio
    async def test_mirror_start_no_device(self, client, web_server):
        web_server["discovery"].renderers = []
        c = await client
        resp = await c.post(
            "/api/mirror/start",
            json={"fps": 30, "quality": "medium", "audio": False},
        )
        assert resp.status == 400
        data = await resp.json()
        assert "error" in data

    @pytest.mark.asyncio
    async def test_mirror_start_success(self, client, web_server):
        device = _make_device()
        web_server["discovery"].renderers = [device]

        mirror = web_server["server"]._mirror
        mirror.start = AsyncMock()

        c = await client
        resp = await c.post(
            "/api/mirror/start",
            json={"fps": 30, "quality": "high", "audio": True},
        )
        data = await resp.json()
        assert data["ok"] is True
        assert data["quality"] == "high"
        assert data["fps"] == 30
        assert data["audio"] is True
        mirror.start.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_mirror_start_already_running(self, client, web_server):
        device = _make_device()
        web_server["discovery"].renderers = [device]

        mirror = web_server["server"]._mirror
        mirror.start = AsyncMock(side_effect=RuntimeError("Already mirroring"))

        c = await client
        resp = await c.post(
            "/api/mirror/start",
            json={"fps": 30, "quality": "medium", "audio": False},
        )
        assert resp.status == 400
        data = await resp.json()
        assert "Already" in data["error"]

    @pytest.mark.asyncio
    async def test_mirror_stop(self, client, web_server):
        mirror = web_server["server"]._mirror
        mirror.stop = AsyncMock()

        c = await client
        resp = await c.post("/api/mirror/stop")
        data = await resp.json()
        assert data["ok"] is True
        mirror.stop.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_mirror_start_default_params(self, client, web_server):
        device = _make_device()
        web_server["discovery"].renderers = [device]

        mirror = web_server["server"]._mirror
        mirror.start = AsyncMock()

        c = await client
        resp = await c.post("/api/mirror/start", json={})
        data = await resp.json()
        assert data["ok"] is True
        assert data["fps"] == 30
        assert data["quality"] == "medium"
        assert data["audio"] is False


# === Library API ===


class TestLibraryAPI:
    @pytest.mark.asyncio
    async def test_browse_without_scan(self, client, web_server):
        c = await client
        resp = await c.get("/api/library/browse?id=0")
        assert resp.status == 400
        data = await resp.json()
        assert "error" in data

    @pytest.mark.asyncio
    async def test_play_without_scan(self, client, web_server):
        c = await client
        resp = await c.post("/api/library/play", json={"id": "1"})
        assert resp.status == 400

    @pytest.mark.asyncio
    async def test_scan_no_directories(self, client, web_server):
        c = await client
        resp = await c.post("/api/library/scan", json={"directories": []})
        assert resp.status == 400

    @pytest.mark.asyncio
    async def test_scan_invalid_directory(self, client, web_server):
        c = await client
        resp = await c.post(
            "/api/library/scan",
            json={"directories": ["/nonexistent/path/xyz123"]},
        )
        assert resp.status == 400

    @pytest.mark.asyncio
    async def test_scan_valid_directory(self, client, web_server, tmp_path):
        media_dir = tmp_path / "media"
        media_dir.mkdir()
        (media_dir / "test.mp4").write_text("fake")
        (media_dir / "song.mp3").write_text("fake")
        (media_dir / "readme.txt").write_text("not media")

        c = await client
        resp = await c.post(
            "/api/library/scan",
            json={"directories": [str(media_dir)]},
        )
        data = await resp.json()
        assert data["ok"] is True
        assert data["total_items"] == 2

    @pytest.mark.asyncio
    async def test_browse_after_scan(self, client, web_server, tmp_path):
        media_dir = tmp_path / "media"
        media_dir.mkdir()
        (media_dir / "movie.mp4").write_text("fake")
        sub = media_dir / "sub"
        sub.mkdir()
        (sub / "clip.mp4").write_text("fake")

        c = await client
        await c.post(
            "/api/library/scan",
            json={"directories": [str(media_dir)]},
        )

        resp = await c.get("/api/library/browse?id=0")
        data = await resp.json()
        assert len(data["items"]) == 2
        titles = [it["title"] for it in data["items"]]
        assert "sub" in titles
        assert "movie.mp4" in titles

    @pytest.mark.asyncio
    async def test_browse_subfolder(self, client, web_server, tmp_path):
        media_dir = tmp_path / "media"
        media_dir.mkdir()
        sub = media_dir / "videos"
        sub.mkdir()
        (sub / "clip.mp4").write_text("fake")

        c = await client
        await c.post(
            "/api/library/scan",
            json={"directories": [str(media_dir)]},
        )

        root_resp = await c.get("/api/library/browse?id=0")
        root_data = await root_resp.json()
        folder = next(it for it in root_data["items"] if it["is_container"])

        resp = await c.get(f"/api/library/browse?id={folder['id']}")
        data = await resp.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["title"] == "clip.mp4"
        assert data["items"][0]["mime_type"].startswith("video/")

    @pytest.mark.asyncio
    async def test_play_library_item(self, client, web_server, tmp_path):
        device = _make_device()
        web_server["discovery"].renderers = [device]

        media_dir = tmp_path / "media"
        media_dir.mkdir()
        (media_dir / "movie.mp4").write_text("fake")

        c = await client
        await c.post(
            "/api/library/scan",
            json={"directories": [str(media_dir)]},
        )

        browse_resp = await c.get("/api/library/browse?id=0")
        items = (await browse_resp.json())["items"]
        media_item = next(it for it in items if not it["is_container"])

        resp = await c.post("/api/library/play", json={"id": media_item["id"]})
        data = await resp.json()
        assert data["ok"] is True
        assert data["title"] == "movie.mp4"
        web_server["controller"].play_file.assert_awaited()

    @pytest.mark.asyncio
    async def test_play_invalid_item(self, client, web_server, tmp_path):
        device = _make_device()
        web_server["discovery"].renderers = [device]

        media_dir = tmp_path / "media"
        media_dir.mkdir()
        (media_dir / "movie.mp4").write_text("fake")

        c = await client
        await c.post(
            "/api/library/scan",
            json={"directories": [str(media_dir)]},
        )

        resp = await c.post("/api/library/play", json={"id": "999"})
        assert resp.status == 400

    @pytest.mark.asyncio
    async def test_play_no_device(self, client, web_server, tmp_path):
        web_server["discovery"].renderers = []

        media_dir = tmp_path / "media"
        media_dir.mkdir()
        (media_dir / "movie.mp4").write_text("fake")

        c = await client
        await c.post(
            "/api/library/scan",
            json={"directories": [str(media_dir)]},
        )

        browse_resp = await c.get("/api/library/browse?id=0")
        items = (await browse_resp.json())["items"]
        media_item = next(it for it in items if not it["is_container"])

        resp = await c.post("/api/library/play", json={"id": media_item["id"]})
        assert resp.status == 400


# === WebSocket ===


class TestWebSocket:
    @pytest.mark.asyncio
    async def test_ws_connect_disconnect(self, client, web_server):
        c = await client
        ws = await c.ws_connect("/ws")
        assert web_server["server"]._ws_clients
        await ws.close()


# === Queue path handling ===


class TestQueueTitles:
    @pytest.mark.asyncio
    async def test_unix_path_title(self, client, web_server):
        c = await client
        await c.post("/api/queue/add", json={"targets": ["/home/user/movie.mp4"]})
        resp = await c.get("/api/queue")
        data = await resp.json()
        assert data["items"][0]["title"] == "movie.mp4"

    @pytest.mark.asyncio
    async def test_url_title(self, client, web_server):
        c = await client
        await c.post(
            "/api/queue/add",
            json={"targets": ["http://example.com/video/test.mp4"]},
        )
        resp = await c.get("/api/queue")
        data = await resp.json()
        assert data["items"][0]["title"] == "test.mp4"

    @pytest.mark.asyncio
    async def test_queue_multiple_add(self, client, web_server):
        c = await client
        await c.post("/api/queue/add", json={"targets": ["/a.mp4", "/b.mkv", "/c.avi"]})
        resp = await c.get("/api/queue")
        data = await resp.json()
        assert len(data["items"]) == 3

    @pytest.mark.asyncio
    async def test_queue_string_target(self, client, web_server):
        """Single string target should be handled."""
        c = await client
        await c.post("/api/queue/add", json={"targets": "/single.mp4"})
        resp = await c.get("/api/queue")
        data = await resp.json()
        assert len(data["items"]) == 1
