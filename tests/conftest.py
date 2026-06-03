"""Shared test fixtures for LanCaster."""

import pytest

from lancaster.models import DeviceType, DLNADevice


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
