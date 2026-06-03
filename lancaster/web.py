"""Web UI and REST API server for LanCaster."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

from aiohttp import WSMsgType, web

from lancaster.controller import MediaController
from lancaster.discovery import DeviceDiscovery
from lancaster.http_server import HTTPFileServer
from lancaster.utils import format_duration, get_local_ip, parse_duration

_LOGGER = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_UPLOAD_DIR = Path.home() / ".lancaster" / "uploads"
_SUBTITLE_EXTS = {".srt", ".ass", ".ssa", ".vtt", ".sub", ".idx"}


@dataclass
class QueueItem:
    target: str
    title: str
    is_url: bool
    subtitle: str | None = None


@dataclass
class ServerSettings:
    poll_interval: float = 2.0
    auto_scan: bool = False
    auto_scan_interval: float = 30.0
    default_volume: int = 50


class WebServer:
    """Combined Web UI + REST API + WebSocket + file serving."""

    def __init__(self, host: str | None = None, port: int = 8200) -> None:
        self._host = host or get_local_ip()
        self._port = port
        self._app = web.Application()
        self._runner: web.AppRunner | None = None

        self._discovery = DeviceDiscovery()
        self._http_server = HTTPFileServer(host=self._host, port=self._port + 1)
        self._controller = MediaController(http_server=self._http_server)
        self._selected_device: str | None = None

        self._queue: list[QueueItem] = []
        self._queue_index: int = -1
        self._queue_playing: bool = False

        self._settings = ServerSettings()

        self._ws_clients: set[web.WebSocketResponse] = set()
        self._status_task: asyncio.Task | None = None
        self._auto_scan_task: asyncio.Task | None = None

        self._setup_routes()

    def _setup_routes(self) -> None:
        r = self._app.router
        r.add_get("/", self._page_index)
        r.add_get("/ws", self._ws_handler)
        r.add_get("/api/devices", self._api_devices)
        r.add_post("/api/devices/select", self._api_select_device)
        r.add_post("/api/cast", self._api_cast)
        r.add_post("/api/control/{action}", self._api_control)
        r.add_get("/api/status", self._api_status)
        r.add_post("/api/upload", self._api_upload)
        r.add_get("/api/queue", self._api_queue_get)
        r.add_post("/api/queue/add", self._api_queue_add)
        r.add_post("/api/queue/remove", self._api_queue_remove)
        r.add_post("/api/queue/clear", self._api_queue_clear)
        r.add_post("/api/queue/play", self._api_queue_play)
        r.add_post("/api/queue/next", self._api_queue_next)
        r.add_post("/api/queue/prev", self._api_queue_prev)
        r.add_post("/api/queue/reorder", self._api_queue_reorder)
        r.add_post("/api/subtitle", self._api_subtitle_upload)
        r.add_get("/api/settings", self._api_settings_get)
        r.add_post("/api/settings", self._api_settings_set)

    @property
    def base_url(self) -> str:
        return f"http://{self._host}:{self._port}"

    async def start(self) -> None:
        await self._http_server.start()
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "0.0.0.0", self._port)
        await site.start()
        self._status_task = asyncio.create_task(self._status_broadcast_loop())
        _LOGGER.info("Web UI available at %s", self.base_url)

    async def stop(self) -> None:
        if self._status_task:
            self._status_task.cancel()
        if self._auto_scan_task:
            self._auto_scan_task.cancel()
        for ws in list(self._ws_clients):
            await ws.close()
        if self._runner:
            await self._runner.cleanup()
        await self._http_server.stop()
        await self._discovery.stop_watch()

    def _get_selected_renderer(self):
        renderers = self._discovery.renderers
        if not renderers:
            return None
        if self._selected_device:
            dev = self._discovery.find_by_name(self._selected_device)
            if dev:
                return dev
        return renderers[0]

    def _build_status_dict(self, info=None, device=None):
        if not device:
            return {
                "device": None, "state": "NO_DEVICE", "position": "00:00:00",
                "duration": "00:00:00", "position_seconds": 0,
                "duration_seconds": 0, "volume": 0, "title": "",
                "queue_index": self._queue_index,
                "queue_length": len(self._queue),
            }
        if info:
            return {
                "device": device.name,
                "state": info.state.value,
                "position": format_duration(info.position),
                "duration": format_duration(info.duration),
                "position_seconds": int(info.position.total_seconds()),
                "duration_seconds": int(info.duration.total_seconds()),
                "volume": info.volume,
                "title": info.title,
                "queue_index": self._queue_index,
                "queue_length": len(self._queue),
            }
        return {
            "device": device.name, "state": "UNKNOWN", "position": "00:00:00",
            "duration": "00:00:00", "position_seconds": 0,
            "duration_seconds": 0, "volume": 0, "title": "",
            "queue_index": self._queue_index,
            "queue_length": len(self._queue),
        }

    async def _broadcast_ws(self, msg: dict) -> None:
        import json as _json
        data = _json.dumps(msg)
        dead = set()
        for ws in self._ws_clients:
            try:
                await ws.send_str(data)
            except Exception:
                dead.add(ws)
        self._ws_clients -= dead

    async def _status_broadcast_loop(self) -> None:
        """Periodically push status to all WebSocket clients."""
        while True:
            try:
                await asyncio.sleep(self._settings.poll_interval)
                if not self._ws_clients:
                    continue
                device = self._get_selected_renderer()
                if not device:
                    status = self._build_status_dict()
                else:
                    try:
                        info = await self._controller.get_position(device)
                        status = self._build_status_dict(info, device)
                        if (
                            self._queue_playing
                            and info.state.value == "STOPPED"
                            and self._queue_index < len(self._queue) - 1
                        ):
                            asyncio.create_task(self._play_next_in_queue())
                    except Exception:
                        status = self._build_status_dict(device=device)
                await self._broadcast_ws({"type": "status", **status})
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(2)

    async def _ws_handler(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self._ws_clients.add(ws)
        _LOGGER.debug("WebSocket client connected (%d total)", len(self._ws_clients))

        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    pass
                elif msg.type in (WSMsgType.ERROR, WSMsgType.CLOSE):
                    break
        finally:
            self._ws_clients.discard(ws)
            _LOGGER.debug("WebSocket client disconnected (%d remain)", len(self._ws_clients))
        return ws

    # --- Page ---

    async def _page_index(self, request: web.Request) -> web.Response:
        html_path = _TEMPLATE_DIR / "index.html"
        if not html_path.exists():
            return web.Response(text="Template not found", status=500)
        return web.Response(
            text=html_path.read_text(encoding="utf-8"),
            content_type="text/html",
        )

    # --- Device APIs ---

    async def _api_devices(self, request: web.Request) -> web.Response:
        timeout = float(request.query.get("timeout", "3"))
        devices = await self._discovery.scan(timeout=timeout)
        result = []
        for d in devices:
            result.append({
                "name": d.name,
                "ip": d.ip,
                "type": d.device_type.value,
                "manufacturer": d.manufacturer,
                "model": d.model,
                "udn": d.udn,
                "selected": (
                    d.name == self._selected_device
                    or (
                        not self._selected_device
                        and self._discovery.renderers
                        and d == self._discovery.renderers[0]
                    )
                ),
            })
        return web.json_response(result)

    async def _api_select_device(self, request: web.Request) -> web.Response:
        data = await request.json()
        name = data.get("name", "")
        self._selected_device = name
        return web.json_response({"ok": True, "selected": name})

    # --- Cast API ---

    async def _api_cast(self, request: web.Request) -> web.Response:
        data = await request.json()
        target = data.get("target", "")
        device = self._get_selected_renderer()
        if not device:
            return web.json_response({"error": "No renderer found"}, status=400)

        try:
            is_url = target.startswith(("http://", "https://"))
            if is_url:
                await self._controller.play_url(
                    device, target, title="LanCaster Web",
                )
            else:
                await self._controller.play_file(device, target)
            return web.json_response(
                {"ok": True, "device": device.name, "target": target},
            )
        except Exception as exc:
            return web.json_response({"error": str(exc)}, status=500)

    async def _api_control(self, request: web.Request) -> web.Response:
        action = request.match_info["action"]
        device = self._get_selected_renderer()
        if not device:
            return web.json_response({"error": "No renderer found"}, status=400)

        try:
            if action == "pause":
                await self._controller.pause(device)
            elif action == "resume":
                await self._controller.resume(device)
            elif action == "stop":
                self._queue_playing = False
                await self._controller.stop(device)
            elif action == "seek":
                data = await request.json()
                pos = parse_duration(data.get("position", "0"))
                await self._controller.seek(device, pos)
            elif action == "volume":
                data = await request.json()
                level = int(data.get("level", 50))
                await self._controller.set_volume(device, level)
            else:
                return web.json_response(
                    {"error": f"Unknown action: {action}"}, status=400,
                )
            return web.json_response({"ok": True, "action": action})
        except Exception as exc:
            return web.json_response({"error": str(exc)}, status=500)

    async def _api_status(self, request: web.Request) -> web.Response:
        device = self._get_selected_renderer()
        if not device:
            return web.json_response(self._build_status_dict())

        try:
            info = await self._controller.get_position(device)
            return web.json_response(self._build_status_dict(info, device))
        except Exception:
            return web.json_response(self._build_status_dict(device=device))

    async def _api_upload(self, request: web.Request) -> web.Response:
        device = self._get_selected_renderer()
        if not device:
            return web.json_response({"error": "No renderer found"}, status=400)

        _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        reader = await request.multipart()

        video_path = None
        subtitle_path = None

        async for part in reader:
            if not part.filename:
                continue
            filename = part.filename
            suffix = Path(filename).suffix.lower()
            filepath = _UPLOAD_DIR / filename

            with open(filepath, "wb") as f:
                while True:
                    chunk = await part.read_chunk()
                    if not chunk:
                        break
                    f.write(chunk)

            if suffix in _SUBTITLE_EXTS:
                subtitle_path = filepath
            elif part.name == "file" or video_path is None:
                video_path = filepath

        if not video_path:
            return web.json_response({"error": "No video file provided"}, status=400)

        try:
            await self._controller.play_file(device, video_path)
            return web.json_response({
                "ok": True, "file": video_path.name,
                "subtitle": subtitle_path.name if subtitle_path else None,
                "device": device.name,
            })
        except Exception as exc:
            return web.json_response({"error": str(exc)}, status=500)

    # --- Queue APIs ---

    async def _api_queue_get(self, request: web.Request) -> web.Response:
        items = []
        for i, q in enumerate(self._queue):
            items.append({
                "index": i, "target": q.target, "title": q.title,
                "is_url": q.is_url, "subtitle": q.subtitle,
                "current": i == self._queue_index,
            })
        return web.json_response({
            "items": items, "index": self._queue_index,
            "playing": self._queue_playing,
        })

    async def _api_queue_add(self, request: web.Request) -> web.Response:
        data = await request.json()
        targets = data.get("targets", [])
        if isinstance(targets, str):
            targets = [targets]
        for t in targets:
            is_url = t.startswith(("http://", "https://"))
            title = t.rsplit("/", 1)[-1] if "/" in t else t
            self._queue.append(QueueItem(
                target=t, title=title, is_url=is_url,
                subtitle=data.get("subtitle"),
            ))
        await self._broadcast_ws({
            "type": "queue", "items": len(self._queue),
        })
        return web.json_response({"ok": True, "length": len(self._queue)})

    async def _api_queue_remove(self, request: web.Request) -> web.Response:
        data = await request.json()
        index = data.get("index", -1)
        if 0 <= index < len(self._queue):
            self._queue.pop(index)
            if index < self._queue_index:
                self._queue_index -= 1
            elif index == self._queue_index:
                self._queue_index = min(
                    self._queue_index, len(self._queue) - 1,
                )
        return web.json_response({"ok": True, "length": len(self._queue)})

    async def _api_queue_clear(self, request: web.Request) -> web.Response:
        self._queue.clear()
        self._queue_index = -1
        self._queue_playing = False
        return web.json_response({"ok": True})

    async def _api_queue_play(self, request: web.Request) -> web.Response:
        data = await request.json()
        index = data.get("index", 0)
        if not self._queue:
            return web.json_response({"error": "Queue is empty"}, status=400)
        index = max(0, min(index, len(self._queue) - 1))
        self._queue_index = index
        self._queue_playing = True
        return await self._play_queue_item(index)

    async def _api_queue_next(self, request: web.Request) -> web.Response:
        if self._queue_index < len(self._queue) - 1:
            self._queue_index += 1
            return await self._play_queue_item(self._queue_index)
        return web.json_response({"error": "Already at end of queue"}, status=400)

    async def _api_queue_prev(self, request: web.Request) -> web.Response:
        if self._queue_index > 0:
            self._queue_index -= 1
            return await self._play_queue_item(self._queue_index)
        return web.json_response({"error": "Already at start of queue"}, status=400)

    async def _api_queue_reorder(self, request: web.Request) -> web.Response:
        data = await request.json()
        from_idx = data.get("from", -1)
        to_idx = data.get("to", -1)
        if (
            0 <= from_idx < len(self._queue)
            and 0 <= to_idx < len(self._queue)
        ):
            item = self._queue.pop(from_idx)
            self._queue.insert(to_idx, item)
            if self._queue_index == from_idx:
                self._queue_index = to_idx
        return web.json_response({"ok": True})

    async def _play_queue_item(self, index: int) -> web.Response:
        device = self._get_selected_renderer()
        if not device:
            return web.json_response({"error": "No renderer found"}, status=400)

        item = self._queue[index]
        try:
            if item.is_url:
                await self._controller.play_url(
                    device, item.target, title=item.title,
                )
            else:
                await self._controller.play_file(device, item.target)
            await self._broadcast_ws({
                "type": "queue_playing", "index": index,
                "title": item.title,
            })
            return web.json_response({
                "ok": True, "index": index, "title": item.title,
            })
        except Exception as exc:
            return web.json_response({"error": str(exc)}, status=500)

    async def _play_next_in_queue(self) -> None:
        if self._queue_index < len(self._queue) - 1:
            self._queue_index += 1
            device = self._get_selected_renderer()
            if device:
                item = self._queue[self._queue_index]
                try:
                    if item.is_url:
                        await self._controller.play_url(
                            device, item.target, title=item.title,
                        )
                    else:
                        await self._controller.play_file(device, item.target)
                    await self._broadcast_ws({
                        "type": "queue_playing",
                        "index": self._queue_index,
                        "title": item.title,
                    })
                except Exception as exc:
                    _LOGGER.error("Failed to play next queue item: %s", exc)
        else:
            self._queue_playing = False

    # --- Subtitle API ---

    async def _api_subtitle_upload(self, request: web.Request) -> web.Response:
        _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        reader = await request.multipart()
        part = await reader.next()
        if not part or not part.filename:
            return web.json_response(
                {"error": "No subtitle file"}, status=400,
            )

        filename = part.filename
        filepath = _UPLOAD_DIR / filename
        with open(filepath, "wb") as f:
            while True:
                chunk = await part.read_chunk()
                if not chunk:
                    break
                f.write(chunk)

        return web.json_response({
            "ok": True, "file": filename, "path": str(filepath),
        })

    # --- Settings API ---

    async def _api_settings_get(self, request: web.Request) -> web.Response:
        s = self._settings
        return web.json_response({
            "poll_interval": s.poll_interval,
            "auto_scan": s.auto_scan,
            "auto_scan_interval": s.auto_scan_interval,
            "default_volume": s.default_volume,
        })

    async def _api_settings_set(self, request: web.Request) -> web.Response:
        data = await request.json()
        s = self._settings
        if "poll_interval" in data:
            s.poll_interval = max(0.5, float(data["poll_interval"]))
        if "auto_scan" in data:
            s.auto_scan = bool(data["auto_scan"])
            if s.auto_scan and not self._auto_scan_task:
                self._auto_scan_task = asyncio.create_task(
                    self._auto_scan_loop(),
                )
            elif not s.auto_scan and self._auto_scan_task:
                self._auto_scan_task.cancel()
                self._auto_scan_task = None
        if "auto_scan_interval" in data:
            s.auto_scan_interval = max(10, float(data["auto_scan_interval"]))
        if "default_volume" in data:
            s.default_volume = max(0, min(100, int(data["default_volume"])))

        return web.json_response({"ok": True})

    async def _auto_scan_loop(self) -> None:
        while self._settings.auto_scan:
            try:
                await asyncio.sleep(self._settings.auto_scan_interval)
                devices = await self._discovery.scan(timeout=3)
                await self._broadcast_ws({
                    "type": "devices",
                    "count": len(devices),
                    "names": [d.name for d in devices],
                })
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(5)
