# LanCaster

A full-featured DLNA video casting tool — cast local videos, online URLs, or even your desktop to any smart TV on the same WiFi network.

> **LAN** + **Caster** = LanCaster

## Features

- **Local file casting** — select a video on your PC and play it on your TV
- **Online URL casting** — send a video URL directly to your TV
- **Media library sharing** — expose folders as a DLNA Media Server for your TV to browse
- **Desktop mirroring** — stream your desktop to the TV in real time (via FFmpeg)

## Quick Start

```bash
pip install -e .

# Discover devices on the network
lancaster discover

# Cast a local video to your TV
lancaster cast movie.mp4

# Cast to a specific device
lancaster cast movie.mp4 -d "Living Room TV"

# Playback control
lancaster pause
lancaster resume
lancaster stop
lancaster seek 01:23:45
lancaster volume 50
```

## Requirements

- Python 3.10+
- FFmpeg (optional, for transcoding and desktop mirroring)
- A DLNA-compatible smart TV on the same WiFi network

## License

MIT
