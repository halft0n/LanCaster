"""Shared test fixtures for LanCaster."""

import asyncio
import sys

import pytest

from lancaster.models import DeviceType, DLNADevice


@pytest.fixture(scope="session", autouse=True)
def _windows_event_loop_policy():
    """Use ProactorEventLoop on Windows for subprocess support."""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest.fixture
def sample_renderer() -> DLNADevice:
    return DLNADevice(
        name="Test TV",
        ip="192.168.1.100",
        location="http://192.168.1.100:49152/description.xml",
        device_type=DeviceType.RENDERER,
        manufacturer="TestCorp",
        model="SmartTV-1000",
        udn="uuid:test-1234",
    )
