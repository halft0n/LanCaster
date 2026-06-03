# LanCaster

A full-featured DLNA video casting tool — cast local videos, online URLs, or even your desktop to any smart TV on the same WiFi network.

> **LAN** + **Caster** = LanCaster

## Features

- **Local file casting** — select a video on your PC and play it on your TV
- **Smart URL casting** — HTTP direct or HTTPS proxied, auto-detected
- **Auto transcoding** — probe media format, auto-transcode incompatible codecs via FFmpeg
- **Web UI** — browser-based control panel with WebSocket real-time updates
- **Playlist queue** — add multiple items, auto-advance, reorder
- **Media library sharing** — expose folders as a DLNA Media Server, TV can browse and play
- **Desktop mirroring** — stream your desktop to the TV in real time via FFmpeg
- **Desktop app** — native window with system tray via pywebview (drag-and-drop casting)

## Quick Start

```bash
pip install -e ".[dev]"
```

### CLI Mode

```bash
# Discover devices on the network
lancaster discover

# Cast a local video (auto-probes + transcodes if needed)
lancaster cast movie.mp4

# Cast to a specific device
lancaster cast movie.mp4 -d "Living Room TV"

# Cast without auto-transcode
lancaster cast movie.mkv --no-transcode

# Cast a URL (auto-detects direct vs proxied)
lancaster cast "http://example.com/video.mp4"      # direct mode
lancaster cast "https://example.com/video.mp4"     # proxied mode
lancaster cast "http://example.com/v.mp4" --force-proxy  # force proxy

# Probe a file without casting
lancaster probe movie.mkv

# Mirror desktop to the TV
lancaster mirror                           # default: medium quality, 30fps
lancaster mirror --quality high --fps 60   # high quality
lancaster mirror --audio                   # include system audio

# Share a media library (TV browses and plays)
lancaster serve ~/Movies ~/Music
lancaster serve /mnt/media -p 9000

# Launch desktop app (native window + system tray)
pip install lancaster[desktop]   # first time only
lancaster desktop

# Playback control
lancaster pause
lancaster resume
lancaster stop
lancaster seek 01:23:45
lancaster volume 50
lancaster status
```

### Web UI Mode

```bash
lancaster web              # Start Web UI on port 8200
lancaster web -p 9000      # Use a custom port
```

Open `http://<your-ip>:8200` in a browser. The Web UI provides:

- **Device discovery** — scan and select DLNA renderers
- **Three casting modes** — URL (smart routing), local file path, or file upload
- **Playlist queue** — add/remove/reorder, auto-advance, prev/next navigation
- **Playback controls** — play/pause, stop, seek, volume, progress bar
- **WebSocket real-time status** — no polling, instant updates
- **Settings panel** — poll interval, auto-scan, default volume
- **Subtitle upload** — drag-and-drop .srt/.ass/.vtt alongside video
- **Upload progress bar** — real-time upload percentage
- **Playback history** — remembers recent casts (localStorage)
- **14 keyboard shortcuts** — Space, arrows, S, M, N, P, D, T, ? and more
- **Dark/Light theme** — toggle with button or `T` key
- **Mobile responsive** — works on phones and tablets

### Desktop App Mode

```bash
pip install lancaster[desktop]
lancaster desktop
```

Native window with the full Web UI, plus system tray icon and file drag-and-drop.

**Build standalone executable:**

```bash
pip install pyinstaller
pyinstaller lancaster.spec
# Output: dist/LanCaster/
```

## Project Structure

```
LanCaster/
├── lancaster/              # Core library
│   ├── models.py           # Data classes (DLNADevice, MediaInfo, PlaybackInfo)
│   ├── discovery.py        # SSDP device discovery
│   ├── controller.py       # DLNA playback control (DMC)
│   ├── transcoder.py       # FFmpeg probe + transcode
│   ├── url_proxy.py        # URL routing (direct / proxied / transcode)
│   ├── http_server.py      # Local file HTTP server with Range support
│   ├── didl.py             # DIDL-Lite XML builder
│   ├── desktop.py          # Desktop GUI (pywebview + pystray)
│   ├── mirror.py           # Desktop mirroring (FFmpeg screen capture)
│   ├── media_server.py     # DLNA Media Server (DMS)
│   ├── web.py              # Web UI server + REST API + WebSocket
│   ├── templates/
│   │   └── index.html      # Single-file frontend (Alpine.js)
│   ├── config.py           # User configuration (~/.lancaster/)
│   ├── utils.py            # Helpers (MIME types, duration formatting)
│   └── exceptions.py       # Custom exceptions
├── lancaster_cli/          # CLI interface
│   ├── app.py              # Click command group
│   └── commands/           # discover, cast, probe, control, web, mirror, serve, desktop
├── tests/                  # 158 unit tests
├── docs/
│   └── ARCHITECTURE.md     # Detailed design document (1100+ lines)
└── pyproject.toml
```

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Async runtime | `asyncio` |
| DLNA/UPnP | `async-upnp-client` |
| HTTP server | `aiohttp` |
| Media probing | FFmpeg `ffprobe` subprocess |
| Transcoding | FFmpeg subprocess (NVENC/QSV/AMF auto-detect) |
| DIDL-Lite XML | `python-didl-lite` |
| CLI framework | `click` + `rich` |
| Web frontend | Alpine.js (CDN, zero build step) |
| Real-time | WebSocket (`aiohttp`) |
| Testing | `pytest` + `pytest-asyncio` + `pytest-aiohttp` |

## REST API

When the Web UI is running (`lancaster web`), these endpoints are available:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/devices` | GET | Scan for DLNA devices |
| `/api/devices/select` | POST | Select active renderer |
| `/api/cast` | POST | Cast URL (smart routing) or file path |
| `/api/upload` | POST | Upload video + optional subtitle and cast |
| `/api/control/{action}` | POST | pause / resume / stop / seek / volume |
| `/api/status` | GET | Current playback state |
| `/api/queue/*` | GET/POST | Playlist queue management |
| `/api/subtitle` | POST | Upload subtitle file |
| `/api/settings` | GET/POST | Server settings |
| `/api/mirror/start` | POST | Start desktop mirroring |
| `/api/mirror/stop` | POST | Stop desktop mirroring |
| `/api/mirror/status` | GET | Mirror running state |
| `/api/library/scan` | POST | Scan directories for media |
| `/api/library/browse` | GET | Browse media library tree |
| `/api/library/play` | POST | Play a library item on TV |
| `/ws` | WebSocket | Real-time status push |

## Requirements

- Python 3.10+
- A DLNA-compatible smart TV on the same WiFi network
- FFmpeg *(optional but recommended — enables transcoding and media probing)*

## Roadmap

- [x] Phase 1: MVP CLI (discover, cast, control)
- [x] Web UI (browser-based control panel with WebSocket + queue)
- [x] Phase 2: FFmpeg transcoder + URL proxy
- [x] Phase 3: Media library sharing (DMS) + desktop mirroring
- [x] Phase 4: Desktop app (pywebview + pystray, drag-and-drop casting)

## License

MIT
