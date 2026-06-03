"""Tests for configuration management."""

import tempfile
from pathlib import Path
from unittest import mock

from lancaster import config


def test_load_save_config():
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg_file = Path(tmpdir) / "config.json"
        with mock.patch.object(config, "_CONFIG_FILE", cfg_file):
            with mock.patch.object(config, "_CONFIG_DIR", Path(tmpdir)):
                config.save_config({"key": "value"})
                loaded = config.load_config()
                assert loaded["key"] == "value"


def test_default_device():
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg_file = Path(tmpdir) / "config.json"
        with mock.patch.object(config, "_CONFIG_FILE", cfg_file):
            with mock.patch.object(config, "_CONFIG_DIR", Path(tmpdir)):
                assert config.get_default_device() is None
                config.set_default_device("Living Room TV")
                assert config.get_default_device() == "Living Room TV"
