"""Configuration management for LanCaster."""

from __future__ import annotations

import json
from pathlib import Path

_CONFIG_DIR = Path.home() / ".lancaster"
_CONFIG_FILE = _CONFIG_DIR / "config.json"


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
