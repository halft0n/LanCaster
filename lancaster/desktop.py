"""Desktop GUI application using pywebview + pystray."""

from __future__ import annotations

import asyncio
import logging
import sys
import threading
from pathlib import Path

_LOGGER = logging.getLogger(__name__)

_ICON_SIZE = 64
_DEFAULT_WIDTH = 1060
_DEFAULT_HEIGHT = 780
_ASSETS_DIR = Path(__file__).parent.parent / "assets"


def _load_tray_image():
    """Load the tray icon image, falling back to a generated one."""
    from PIL import Image, ImageDraw

    icon_path = _ASSETS_DIR / "icon-64.png"
    if icon_path.exists():
        return Image.open(icon_path).convert("RGBA")

    img = Image.new("RGBA", (_ICON_SIZE, _ICON_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle(
        [4, 4, _ICON_SIZE - 4, _ICON_SIZE - 4],
        radius=12,
        fill=(108, 92, 231),
    )
    draw.text((_ICON_SIZE // 2 - 8, _ICON_SIZE // 2 - 12), "L", fill="white")
    return img


def _create_tray_icon(
    show_cb: callable,
    quit_cb: callable,
) -> None:
    """Create a system tray icon in a separate thread."""
    try:
        import pystray
    except ImportError:
        _LOGGER.warning("pystray/Pillow not installed, skipping tray icon")
        return

    img = _load_tray_image()

    menu = pystray.Menu(
        pystray.MenuItem("显示窗口", lambda: show_cb(), default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("退出", lambda: quit_cb()),
    )

    icon = pystray.Icon("lancaster", img, "LanCaster", menu)

    def _run():
        icon.run()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return icon


class DesktopApp:
    """Wraps WebServer in a pywebview native window with system tray."""

    def __init__(
        self,
        host: str | None = None,
        port: int = 8200,
        debug: bool = False,
    ) -> None:
        self._host = host
        self._port = port
        self._debug = debug
        self._web_server = None
        self._window = None
        self._tray_icon = None
        self._loop = None
        self._server_thread = None

    def _start_server_in_thread(self) -> None:
        """Run the aiohttp WebServer in a background thread with its own event loop."""
        from lancaster.web import WebServer

        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        self._loop = asyncio.new_event_loop()
        self._web_server = WebServer(host=self._host, port=self._port)

        async def _run():
            await self._web_server.start()
            try:
                while True:
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                pass
            finally:
                await self._web_server.stop()

        self._server_task = self._loop.create_task(_run())

        def _thread_target():
            asyncio.set_event_loop(self._loop)
            self._loop.run_until_complete(self._server_task)

        self._server_thread = threading.Thread(target=_thread_target, daemon=True)
        self._server_thread.start()

    def _stop_server(self) -> None:
        if self._loop and self._server_task:
            self._loop.call_soon_threadsafe(self._server_task.cancel)

    def _on_shown(self) -> None:
        """Called when the pywebview window is first shown."""
        self._tray_icon = _create_tray_icon(
            show_cb=self._show_window,
            quit_cb=self._quit,
        )

    def _on_closing(self) -> bool:
        """Called when user tries to close the window. Returns False to cancel close."""
        self._stop_server()
        return True

    def _show_window(self) -> None:
        if self._window:
            self._window.show()
            self._window.restore()

    def _quit(self) -> None:
        self._stop_server()
        if self._window:
            self._window.destroy()

    def _expose_api(self) -> _DesktopBridge:
        """Create a JS-callable bridge object."""
        return _DesktopBridge(self)

    def run(self) -> None:
        """Launch the desktop application."""
        try:
            import webview
        except ImportError:
            print(
                "pywebview is required for desktop mode.\n"
                "Install it with: pip install lancaster[desktop]"
            )
            sys.exit(1)

        self._start_server_in_thread()

        import time

        time.sleep(0.5)

        url = f"http://127.0.0.1:{self._port}"
        bridge = self._expose_api()

        self._window = webview.create_window(
            "LanCaster",
            url=url,
            width=_DEFAULT_WIDTH,
            height=_DEFAULT_HEIGHT,
            min_size=(480, 400),
            js_api=bridge,
            text_select=self._debug,
            confirm_close=not self._debug,
        )
        self._window.events.shown += self._on_shown
        self._window.events.closing += self._on_closing

        webview.start(debug=self._debug)

        self._stop_server()


class _DesktopBridge:
    """Python API exposed to JavaScript via pywebview's js_api.

    JS can call these methods via `window.pywebview.api.<method>()`.
    """

    def __init__(self, app: DesktopApp) -> None:
        self._app = app

    def cast_dropped_files(self, file_paths: list[str]) -> dict:
        """Handle files dropped onto the window from the OS file manager."""
        if not file_paths:
            return {"ok": False, "error": "No files"}

        media_exts = {
            ".mp4",
            ".mkv",
            ".avi",
            ".mov",
            ".wmv",
            ".flv",
            ".webm",
            ".ts",
            ".m4v",
            ".mpg",
            ".mpeg",
            ".3gp",
            ".ogv",
            ".mp3",
            ".flac",
            ".wav",
            ".aac",
            ".ogg",
            ".wma",
            ".m4a",
        }
        subtitle_exts = {".srt", ".ass", ".ssa", ".vtt", ".sub"}

        video_file = None
        subtitle_file = None

        for fp in file_paths:
            ext = Path(fp).suffix.lower()
            if ext in subtitle_exts:
                subtitle_file = fp
            elif ext in media_exts:
                video_file = fp

        if not video_file and file_paths:
            video_file = file_paths[0]

        return {
            "ok": True,
            "video": video_file,
            "subtitle": subtitle_file,
        }

    def open_file_dialog(self) -> dict:
        """Open a native file picker dialog via pywebview."""
        if not self._app._window:
            return {"ok": False, "error": "Window not available"}

        file_types = (
            "视频文件 (*.mp4;*.mkv;*.avi;*.mov;*.wmv;*.flv;*.webm;*.ts;*.m4v;*.mpg;*.mpeg;*.3gp;*.ogv)",
            "音频文件 (*.mp3;*.flac;*.wav;*.aac;*.ogg;*.wma;*.m4a)",
            "所有文件 (*.*)",
        )
        result = self._app._window.create_file_dialog(
            dialog_type=10,  # OPEN_DIALOG
            allow_multiple=False,
            file_types=file_types,
        )
        if result and len(result) > 0:
            return {"ok": True, "path": result[0]}
        return {"ok": False, "path": None}

    def get_platform(self) -> str:
        return sys.platform

    def minimize_to_tray(self) -> None:
        if self._app._window:
            self._app._window.hide()
