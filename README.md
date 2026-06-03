# LanCaster

A full-featured DLNA video casting tool — cast local videos, online URLs, or even your desktop to any smart TV on the same WiFi network.

> **LAN** + **Caster** = LanCaster

## Features

- **Local file casting** — select a video on your PC and play it on your TV
- **Online URL casting** — send a video URL directly to your TV
- **Web UI** — browser-based control panel with device discovery, casting, and playback controls
- **Media library sharing** — expose folders as a DLNA Media Server for your TV to browse *(planned)*
- **Desktop mirroring** — stream your desktop to the TV in real time via FFmpeg *(planned)*

## Quick Start

```bash
pip install -e ".[dev]"
```

### CLI Mode

```bash
# Discover devices on the network
lancaster discover

# Cast a local video to your TV
lancaster cast movie.mp4

# Cast to a specific device
lancaster cast movie.mp4 -d "Living Room TV"

# Cast a URL
lancaster cast "https://example.com/video.mp4"

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
- **Three casting modes** — URL, local file path, or file upload with progress bar
- **Playback controls** — play/pause, stop, seek, volume, progress bar
- **Playback history** — remembers recent casts (stored in browser localStorage)
- **Keyboard shortcuts** — Space (play/pause), arrows (seek/volume), S (stop), M (mute), and more — press `?` to view all
- **Dark/Light theme** — toggle with button or `T` key
- **Mobile responsive** — works on phones and tablets

## Project Structure

```
LanCaster/
├── lancaster/              # Core library
│   ├── models.py           # Data classes (DLNADevice, PlaybackInfo, etc.)
│   ├── discovery.py        # SSDP device discovery
│   ├── controller.py       # DLNA playback control (DMC)
│   ├── http_server.py      # Local file HTTP server with Range support
│   ├── didl.py             # DIDL-Lite XML builder
│   ├── web.py              # Web UI server + REST API
│   ├── templates/
│   │   └── index.html      # Single-file frontend (Alpine.js)
│   ├── config.py           # User configuration (~/.lancaster/)
│   ├── utils.py            # Helpers (MIME types, duration formatting)
│   └── exceptions.py       # Custom exceptions
├── lancaster_cli/          # CLI interface
│   ├── app.py              # Click command group
│   └── commands/           # discover, cast, control, web
├── tests/                  # 42 unit tests
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
| DIDL-Lite XML | `python-didl-lite` |
| CLI framework | `click` + `rich` |
| Web frontend | Alpine.js (CDN, zero build step) |
| Testing | `pytest` + `pytest-asyncio` + `pytest-aiohttp` |

## REST API

When the Web UI is running, the following API endpoints are available:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/devices` | GET | Scan for DLNA devices |
| `/api/devices/select` | POST | Select active renderer |
| `/api/cast` | POST | Cast URL or file path |
| `/api/upload` | POST | Upload and cast a file |
| `/api/control/{action}` | POST | pause / resume / stop / seek / volume |
| `/api/status` | GET | Current playback state |

## Requirements

- Python 3.10+
- A DLNA-compatible smart TV on the same WiFi network
- FFmpeg *(optional, for future transcoding and desktop mirroring)*

## Roadmap

- [x] Phase 1: MVP CLI (discover, cast, control)
- [x] Web UI (browser-based control panel)
- [ ] Phase 2: FFmpeg transcoding + URL proxy
- [ ] Phase 3: Media library sharing (DMS) + desktop mirroring
- [ ] Phase 4: Native GUI (PyQt6 or Tauri)

## License

MIT
