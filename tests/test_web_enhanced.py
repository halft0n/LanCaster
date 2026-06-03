"""Tests for Web server enhancements (stall detection, resume, manual device, transcode)."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp.test_utils import TestClient, TestServer

from lancaster.models import (
    DeviceType,
    DLNADevice,
    PlaybackInfo,
    TransportState,
)
from lancaster.web import WebServer


def _make_device(name="Test TV", ip="192.168.1.100"):
    return DLNADevice(
        name=name,
        ip=ip,
        location=f"http://{ip}:49152/description.xml",
        device_type=DeviceType.RENDERER,
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
        mock_http_inst.serve_stream = MagicMock(
            return_value="http://localhost/stream/x"
        )
        mock_http.return_value = mock_http_inst

        mock_disc_inst = MagicMock()
        mock_disc_inst.scan = AsyncMock(return_value=[])
        mock_disc_inst.renderers = []
        mock_disc_inst.stop_watch = AsyncMock()
        mock_disc_inst.watch = AsyncMock()
        mock_disc_inst.find_by_name = MagicMock(return_value=None)
        mock_disc_inst.add_device_by_location = AsyncMock()
        mock_disc_inst._source_ip = None
        mock_disc.return_value = mock_disc_inst

        mock_ctrl_inst = MagicMock()
        mock_ctrl_inst.play_url = AsyncMock()
        mock_ctrl_inst.play_file = AsyncMock()
        mock_ctrl_inst.pause = AsyncMock()
        mock_ctrl_inst.resume = AsyncMock()
        mock_ctrl_inst.stop = AsyncMock()
        mock_ctrl_inst.seek = AsyncMock()
        mock_ctrl_inst.set_volume = AsyncMock()
        mock_ctrl_inst.get_position = AsyncMock(
            return_value=PlaybackInfo(
                state=TransportState.STOPPED,
                position=timedelta(),
                duration=timedelta(),
                volume=50,
                title="",
            )
        )
        mock_ctrl_inst.invalidate = MagicMock()
        mock_ctrl.return_value = mock_ctrl_inst

        server = WebServer(host="127.0.0.1", port=18200)
        yield server


@pytest.fixture
async def client(web_server):
    app = web_server._app
    async with TestClient(TestServer(app)) as c:
        yield c


class TestResumeAPI:
    @pytest.mark.asyncio
    async def test_resume_no_target_returns_error(self, client):
        resp = await client.get("/api/resume")
        assert resp.status == 400

    @pytest.mark.asyncio
    async def test_resume_not_found(self, client):
        resp = await client.get("/api/resume?target=unknown.mp4")
        data = await resp.json()
        assert data["ok"] is False

    @pytest.mark.asyncio
    async def test_resume_found(self, client):
        with patch(
            "lancaster.web.get_playback_position",
            return_value={"position": 120, "duration": 3600, "title": "Test", "ts": 1000},
        ):
            resp = await client.get(
                "/api/resume?target=http%3A%2F%2Fexample.com%2Fvideo.mp4"
            )
            data = await resp.json()
            assert data["ok"] is True
            assert data["position"] == 120


class TestAddDeviceAPI:
    @pytest.mark.asyncio
    async def test_add_device_missing_target(self, client):
        resp = await client.post(
            "/api/devices/add",
            json={},
        )
        assert resp.status == 400

    @pytest.mark.asyncio
    async def test_add_device_success(self, client, web_server):
        device = _make_device("Manual TV")
        web_server._discovery.add_device_by_location = AsyncMock(
            return_value=device
        )
        resp = await client.post(
            "/api/devices/add",
            json={"target": "http://192.168.1.200:49152/desc.xml"},
        )
        data = await resp.json()
        assert data["ok"] is True
        assert data["name"] == "Manual TV"

    @pytest.mark.asyncio
    async def test_add_device_failure(self, client, web_server):
        web_server._discovery.add_device_by_location = AsyncMock(
            return_value=None
        )
        resp = await client.post(
            "/api/devices/add",
            json={"target": "192.168.1.200"},
        )
        assert resp.status == 400

    @pytest.mark.asyncio
    async def test_add_device_by_ip(self, client, web_server):
        device = _make_device("IP TV")
        web_server._discovery.add_device_by_location = AsyncMock(
            return_value=device
        )
        resp = await client.post(
            "/api/devices/add",
            json={"target": "192.168.1.200"},
        )
        data = await resp.json()
        assert data["ok"] is True
        web_server._discovery.add_device_by_location.assert_awaited_with(
            "http://192.168.1.200:49152/description.xml"
        )


class TestStallDetection:
    @pytest.mark.asyncio
    async def test_stall_detected_and_seek(self, web_server):
        device = _make_device()
        web_server._selected_device = device.name
        web_server._discovery.renderers = [device]

        playing_info = PlaybackInfo(
            state=TransportState.PLAYING,
            position=timedelta(seconds=100),
            duration=timedelta(seconds=3600),
            volume=50,
            title="test.mp4",
        )

        web_server._last_position_seconds = 100
        web_server._stall_count = 4

        with patch.object(web_server, "_get_selected_renderer", return_value=device):
            await web_server._check_stall(playing_info)

        web_server._controller.seek.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_stall_when_position_advances(self, web_server):
        info = PlaybackInfo(
            state=TransportState.PLAYING,
            position=timedelta(seconds=105),
            duration=timedelta(seconds=3600),
            volume=50,
            title="test.mp4",
        )
        web_server._last_position_seconds = 100
        web_server._stall_count = 3

        await web_server._check_stall(info)
        assert web_server._stall_count == 0

    @pytest.mark.asyncio
    async def test_no_stall_when_stopped(self, web_server):
        info = PlaybackInfo(
            state=TransportState.STOPPED,
            position=timedelta(seconds=100),
            duration=timedelta(seconds=3600),
            volume=50,
            title="test.mp4",
        )
        web_server._last_position_seconds = 100
        web_server._stall_count = 10

        await web_server._check_stall(info)
        assert web_server._stall_count == 0


class TestQueueAdvanceGuard:
    @pytest.mark.asyncio
    async def test_no_advance_when_not_playing_queue(self, web_server):
        web_server._queue_playing = False

        info = PlaybackInfo(
            state=TransportState.STOPPED,
            position=timedelta(seconds=3597),
            duration=timedelta(seconds=3600),
            volume=50,
            title="",
        )
        await web_server._check_queue_advance(info)

    @pytest.mark.asyncio
    async def test_no_advance_when_already_advancing(self, web_server):
        web_server._queue_playing = True
        web_server._advancing = True

        info = PlaybackInfo(
            state=TransportState.STOPPED,
            position=timedelta(seconds=3598),
            duration=timedelta(seconds=3600),
            volume=50,
            title="",
        )
        await web_server._check_queue_advance(info)

    @pytest.mark.asyncio
    async def test_advance_on_natural_end(self, web_server):
        from lancaster.web import QueueItem

        web_server._queue_playing = True
        web_server._queue = [
            QueueItem("a.mp4", "A", False),
            QueueItem("b.mp4", "B", False),
        ]
        web_server._queue_index = 0

        device = _make_device()
        web_server._selected_device = device.name
        web_server._discovery.renderers = [device]

        info = PlaybackInfo(
            state=TransportState.STOPPED,
            position=timedelta(seconds=3598),
            duration=timedelta(seconds=3600),
            volume=50,
            title="",
        )

        with patch.object(web_server, "_get_selected_renderer", return_value=device):
            with patch.object(web_server, "_broadcast_ws", new=AsyncMock()):
                await web_server._check_queue_advance(info)

        assert web_server._queue_index == 1
        assert web_server._advancing is False


class TestDeviceChangeCallback:
    def test_on_device_change_offline_invalidates(self, web_server):
        device = _make_device()
        web_server._on_device_change(device, False)
        web_server._controller.invalidate.assert_called_with(device.udn)

    def test_on_device_change_online_also_invalidates(self, web_server):
        """Location change triggers invalidation regardless of online status."""
        device = _make_device()
        web_server._on_device_change(device, True)
        web_server._controller.invalidate.assert_called_with(device.udn)
