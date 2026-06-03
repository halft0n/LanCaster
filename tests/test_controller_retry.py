"""Tests for MediaController retry, cache invalidation, and locking."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lancaster.controller import _MAX_RETRIES, MediaController
from lancaster.exceptions import PlaybackError
from lancaster.models import DeviceType, DLNADevice, TransportState


def _make_device(name="Test TV"):
    return DLNADevice(
        name=name,
        ip="192.168.1.100",
        location="http://192.168.1.100:49152/description.xml",
        device_type=DeviceType.RENDERER,
        udn=f"uuid:{name.lower().replace(' ', '-')}",
    )


class TestCacheInvalidation:
    def test_invalidate_removes_entry(self):
        ctrl = MediaController()
        ctrl._dmr_cache["uuid:tv"] = MagicMock()
        ctrl.invalidate("uuid:tv")
        assert "uuid:tv" not in ctrl._dmr_cache

    def test_invalidate_nonexistent_no_error(self):
        ctrl = MediaController()
        ctrl.invalidate("uuid:nonexistent")

    def test_invalidate_all_clears_cache(self):
        ctrl = MediaController()
        ctrl._dmr_cache["a"] = MagicMock()
        ctrl._dmr_cache["b"] = MagicMock()
        ctrl.invalidate_all()
        assert len(ctrl._dmr_cache) == 0


class TestPerUDNLock:
    def test_get_lock_creates_new(self):
        ctrl = MediaController()
        lock = ctrl._get_lock("uuid:tv")
        assert isinstance(lock, asyncio.Lock)

    def test_get_lock_returns_same(self):
        ctrl = MediaController()
        lock1 = ctrl._get_lock("uuid:tv")
        lock2 = ctrl._get_lock("uuid:tv")
        assert lock1 is lock2

    def test_different_udns_different_locks(self):
        ctrl = MediaController()
        lock1 = ctrl._get_lock("uuid:tv1")
        lock2 = ctrl._get_lock("uuid:tv2")
        assert lock1 is not lock2


class TestRetryMechanism:
    @pytest.mark.asyncio
    async def test_play_url_succeeds_first_try(self):
        ctrl = MediaController()
        device = _make_device()
        mock_dmr = MagicMock()
        mock_dmr.async_set_transport_uri = AsyncMock()
        mock_dmr.async_wait_for_can_play = AsyncMock()
        mock_dmr.async_play = AsyncMock()

        with patch.object(ctrl, "_get_dmr", new=AsyncMock(return_value=mock_dmr)):
            await ctrl.play_url(device, "http://example.com/video.mp4")

        mock_dmr.async_play.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_play_url_retries_on_transient_failure(self):
        ctrl = MediaController()
        device = _make_device()

        mock_dmr = MagicMock()
        mock_dmr.async_set_transport_uri = AsyncMock(
            side_effect=[OSError("timeout"), None]
        )
        mock_dmr.async_wait_for_can_play = AsyncMock()
        mock_dmr.async_play = AsyncMock()

        with patch.object(ctrl, "_get_dmr", new=AsyncMock(return_value=mock_dmr)):
            with patch("asyncio.sleep", new=AsyncMock()):
                await ctrl.play_url(device, "http://example.com/video.mp4")

        assert mock_dmr.async_set_transport_uri.await_count == 2

    @pytest.mark.asyncio
    async def test_play_url_raises_after_max_retries(self):
        ctrl = MediaController()
        device = _make_device()

        mock_dmr = MagicMock()
        mock_dmr.async_set_transport_uri = AsyncMock(
            side_effect=ConnectionError("always fail")
        )
        mock_dmr.async_wait_for_can_play = AsyncMock()
        mock_dmr.async_play = AsyncMock()

        with patch.object(ctrl, "_get_dmr", new=AsyncMock(return_value=mock_dmr)):
            with patch("asyncio.sleep", new=AsyncMock()):
                with pytest.raises(PlaybackError):
                    await ctrl.play_url(device, "http://x.com/v.mp4")

        assert mock_dmr.async_set_transport_uri.await_count == _MAX_RETRIES + 1

    @pytest.mark.asyncio
    async def test_non_transient_error_not_retried(self):
        ctrl = MediaController()
        device = _make_device()

        mock_dmr = MagicMock()
        mock_dmr.async_set_transport_uri = AsyncMock(
            side_effect=ValueError("bad arg")
        )
        mock_dmr.async_wait_for_can_play = AsyncMock()
        mock_dmr.async_play = AsyncMock()

        with patch.object(ctrl, "_get_dmr", new=AsyncMock(return_value=mock_dmr)):
            with pytest.raises(PlaybackError):
                await ctrl.play_url(device, "http://x.com/v.mp4")

        assert mock_dmr.async_set_transport_uri.await_count == 1

    @pytest.mark.asyncio
    async def test_stop_retries(self):
        ctrl = MediaController()
        device = _make_device()

        mock_dmr = MagicMock()
        mock_dmr.async_stop = AsyncMock(
            side_effect=[OSError("net error"), None]
        )

        with patch.object(ctrl, "_get_dmr", new=AsyncMock(return_value=mock_dmr)):
            with patch("asyncio.sleep", new=AsyncMock()):
                await ctrl.stop(device)

        assert mock_dmr.async_stop.await_count == 2

    @pytest.mark.asyncio
    async def test_invalidate_called_on_retry(self):
        ctrl = MediaController()
        device = _make_device()
        ctrl._dmr_cache[device.udn] = MagicMock()

        mock_dmr = MagicMock()
        mock_dmr.async_pause = AsyncMock(
            side_effect=[TimeoutError("fail"), None]
        )

        with patch.object(ctrl, "_get_dmr", new=AsyncMock(return_value=mock_dmr)):
            with patch("asyncio.sleep", new=AsyncMock()):
                await ctrl.pause(device)

        assert device.udn not in ctrl._dmr_cache


class TestGetPosition:
    @pytest.mark.asyncio
    async def test_get_position_success(self):
        ctrl = MediaController()
        device = _make_device()

        transport_action = AsyncMock(return_value={"CurrentTransportState": "PLAYING"})
        position_action = AsyncMock(
            return_value={
                "RelTime": "0:05:30",
                "TrackDuration": "1:30:00",
                "TrackURI": "http://example.com/video.mp4",
            }
        )
        volume_action = AsyncMock(return_value={"CurrentVolume": 75})

        mock_dmr = MagicMock()

        def fake_action(svc, name):
            if svc == "AVT" and name == "GetTransportInfo":
                m = MagicMock()
                m.async_call = transport_action
                return m
            elif svc == "AVT" and name == "GetPositionInfo":
                m = MagicMock()
                m.async_call = position_action
                return m
            elif svc == "RC" and name == "GetVolume":
                m = MagicMock()
                m.async_call = volume_action
                return m
            return None

        mock_dmr._action = fake_action
        with patch.object(ctrl, "_get_dmr", new=AsyncMock(return_value=mock_dmr)):
            info = await ctrl.get_position(device)

        assert info.state == TransportState.PLAYING
        assert info.position == timedelta(hours=0, minutes=5, seconds=30)
        assert info.volume == 75

    @pytest.mark.asyncio
    async def test_get_position_both_fail_raises(self):
        ctrl = MediaController()
        device = _make_device()

        mock_dmr = MagicMock()

        def fail_action(svc, name):
            m = MagicMock()
            m.async_call = AsyncMock(side_effect=Exception("dead"))
            return m

        mock_dmr._action = fail_action
        with patch.object(ctrl, "_get_dmr", new=AsyncMock(return_value=mock_dmr)):
            with pytest.raises(PlaybackError, match="Device unreachable"):
                await ctrl.get_position(device)


class TestGetVolume:
    @pytest.mark.asyncio
    async def test_get_volume_failure_raises(self):
        ctrl = MediaController()
        device = _make_device()

        mock_dmr = MagicMock()
        vol_action = MagicMock()
        vol_action.async_call = AsyncMock(side_effect=Exception("no"))
        mock_dmr._action = MagicMock(return_value=vol_action)

        with patch.object(ctrl, "_get_dmr", new=AsyncMock(return_value=mock_dmr)):
            with pytest.raises(PlaybackError, match="Failed to get volume"):
                await ctrl.get_volume(device)


class TestConfigurableWait:
    def test_default_wait_time(self):
        ctrl = MediaController()
        assert ctrl._wait_for_play == 15

    def test_custom_wait_time(self):
        ctrl = MediaController(wait_for_play=30)
        assert ctrl._wait_for_play == 30
