"""Configuration management for LanCaster."""

from __future__ import annotations

import json
import time
from pathlib import Path

_CONFIG_DIR = Path.home() / ".lancaster"
_CONFIG_FILE = _CONFIG_DIR / "config.json"
_PROGRESS_FILE = _CONFIG_DIR / "playback_progress.json"

_MAX_PROGRESS_ENTRIES = 200


def _ensure_dir() -> None:
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> dict:
    """Load configuration from disk."""
    if not _CONFIG_FILE.exists():
        return {}
    return json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))


def save_config(cfg: dict) -> None:
    """Save configuration to disk."""
    _ensure_dir()
    _CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


def get_default_device() -> str | None:
    """Return the configured default device name, if any."""
    return load_config().get("default_device")


def set_default_device(name: str) -> None:
    """Store the default device name."""
    cfg = load_config()
    cfg["default_device"] = name
    save_config(cfg)


# --- Playback progress persistence ---


def _load_progress() -> dict:
    if not _PROGRESS_FILE.exists():
        return {}
    try:
        return json.loads(_PROGRESS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_progress(data: dict) -> None:
    _ensure_dir()
    if len(data) > _MAX_PROGRESS_ENTRIES:
        sorted_keys = sorted(data.keys(), key=lambda k: data[k].get("ts", 0))
        for k in sorted_keys[: len(data) - _MAX_PROGRESS_ENTRIES]:
            del data[k]
    _PROGRESS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def save_playback_position(
    target: str,
    position_seconds: int,
    duration_seconds: int,
    title: str = "",
) -> None:
    """Save playback progress for a media target."""
    if position_seconds <= 5 or duration_seconds <= 0:
        return
    if position_seconds >= duration_seconds - 5:
        remove_playback_position(target)
        return

    data = _load_progress()
    data[target] = {
        "position": position_seconds,
        "duration": duration_seconds,
        "title": title,
        "ts": int(time.time()),
    }
    _save_progress(data)


def get_playback_position(target: str) -> dict | None:
    """Get saved playback progress for a target. Returns None if not found."""
    data = _load_progress()
    return data.get(target)


def remove_playback_position(target: str) -> None:
    """Remove saved progress (e.g., after finishing)."""
    data = _load_progress()
    if target in data:
        del data[target]
        _save_progress(data)
