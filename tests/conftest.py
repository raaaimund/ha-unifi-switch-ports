"""Fixtures for UniFi Switch Ports tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from homeassistant.const import CONF_API_KEY, CONF_URL, CONF_VERIFY_SSL
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.unifi_switch_ports.const import CONF_SITE, DOMAIN

if TYPE_CHECKING:
    from pytest_homeassistant_custom_component.test_util.aiohttp import (
        AiohttpClientMocker,
    )

URL = "https://192.168.1.1"
API = f"{URL}/proxy/network/api"
SITE_ID = "00000000-0000-4000-8000-000000000001"

ENTRY_DATA = {
    CONF_URL: URL,
    CONF_API_KEY: "secret-key",
    CONF_VERIFY_SSL: False,
    CONF_SITE: "default",
}


def load_fixture(name: str) -> dict[str, Any]:
    """Load a JSON fixture."""
    return json.loads((Path(__file__).parent / "fixtures" / name).read_text())


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable loading the integration from custom_components."""


@pytest.fixture
def mock_api(aioclient_mock: AiohttpClientMocker) -> AiohttpClientMocker:
    """Mock a UniFi OS console with one site."""
    aioclient_mock.get(f"{API}/self/sites", json=load_fixture("self_sites.json"))
    aioclient_mock.get(
        f"{API}/s/default/stat/device", json=load_fixture("stat_device.json")
    )
    aioclient_mock.get(f"{API}/s/default/stat/sta", json=load_fixture("stat_sta.json"))
    return aioclient_mock


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """Return the config entry of the default site."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Default (192.168.1.1)",
        data=ENTRY_DATA,
        unique_id=SITE_ID,
    )
