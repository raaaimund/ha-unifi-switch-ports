"""Tests for setup, sensors and the websocket API."""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import device_registry as dr

from custom_components.unifi_switch_ports.const import DOMAIN, RELOAD_NOTIFICATION_ID

from .conftest import API

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from pytest_homeassistant_custom_component.test_util.aiohttp import (
        AiohttpClientMocker,
    )
    from pytest_homeassistant_custom_component.typing import WebSocketGenerator


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.usefixtures("mock_api")
async def test_setup_and_unload(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """The entry loads and unloads."""
    await _setup(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.NOT_LOADED


@pytest.mark.usefixtures("mock_api")
async def test_sensors_and_devices(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Every switch gets a device with its sensors; APs are ignored."""
    await _setup(hass, config_entry)

    assert hass.states.get("sensor.rack_switch_ports_up").state == "6"
    assert hass.states.get("sensor.rack_switch_poe_power").state == "26.5"
    assert hass.states.get("sensor.ucg_fiber_ports_up").state == "3"
    assert hass.states.get("sensor.office_switch_ports_up").state == "4"
    # A switch without PoE ports has no PoE sensor.
    assert hass.states.get("sensor.office_switch_poe_power") is None
    # Offline switches are unavailable.
    assert hass.states.get("sensor.us_8_ports_up").state == "unavailable"

    device = device_registry.async_get_device_by_identifier(
        (DOMAIN, "aa:00:00:00:00:75"), config_entry.entry_id
    )
    assert device.model == "USW Flex 2.5G 8 PoE"
    assert device.model_id == "USWED37"
    assert (dr.CONNECTION_NETWORK_MAC, "aa:00:00:00:00:75") in device.connections
    assert (
        len(dr.async_entries_for_config_entry(device_registry, config_entry.entry_id))
        == 4
    )


async def test_auth_failure_starts_reauth(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> None:
    """A rejected API key puts the entry into reauth."""
    aioclient_mock.get(
        f"{API}/s/default/stat/device", status=HTTPStatus.UNAUTHORIZED, json={}
    )
    aioclient_mock.get(
        f"{API}/s/default/stat/sta", status=HTTPStatus.UNAUTHORIZED, json={}
    )
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert [flow["context"]["source"] for flow in flows] == ["reauth"]


async def test_connection_error_retries(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> None:
    """An unreachable controller retries the setup later."""
    aioclient_mock.get(f"{API}/s/default/stat/device", exc=TimeoutError)
    aioclient_mock.get(f"{API}/s/default/stat/sta", exc=TimeoutError)
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


@pytest.mark.usefixtures("mock_api")
async def test_websocket_subscribe(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    config_entry: MockConfigEntry,
) -> None:
    """The card gets all switches, gateway first, then after every update."""
    await _setup(hass, config_entry)
    client = await hass_ws_client(hass)

    await client.send_json_auto_id({"type": f"{DOMAIN}/subscribe"})
    result = await client.receive_json()
    assert result["success"]

    event = (await client.receive_json())["event"]
    assert event["entry_id"] == config_entry.entry_id
    assert event["available"] is True
    names = [switch["name"] for switch in event["switches"]]
    assert names == ["UCG Fiber", "Office Switch", "Rack Switch", "US 8"]

    rack = event["switches"][2]
    assert rack["model_name"] == "USW Flex 2.5G 8 PoE"
    assert rack["layout"] == [[1, 2, 3, 4, 5, 6, 7, 8, None, 9, 10]]
    port10 = rack["ports"][9]
    assert port10["uplink"] is True
    assert port10["combo"] is True
    assert port10["sfp_module"] == "UF-MM-10G"
    assert port10["neighbours"] == [
        {"name": "UCG Fiber", "detail": "UCG Fiber · 192.0.2.1", "device": True}
    ]

    await config_entry.runtime_data.async_refresh()
    event = (await client.receive_json())["event"]
    assert len(event["switches"]) == 4


@pytest.mark.usefixtures("mock_api")
async def test_websocket_unknown_entry(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    config_entry: MockConfigEntry,
) -> None:
    """An unknown entry id is an error."""
    await _setup(hass, config_entry)
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": f"{DOMAIN}/subscribe", "entry_id": "nope"})
    result = await client.receive_json()
    assert not result["success"]
    assert result["error"]["code"] == "not_found"


@pytest.mark.usefixtures("mock_api")
async def test_reload_notification(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    config_entry: MockConfigEntry,
) -> None:
    """Adding the card at runtime asks to reload the browser until a card runs."""
    hass.config.components.add("frontend")
    with patch(
        "custom_components.unifi_switch_ports.add_extra_js_url"
    ) as add_extra_js_url:
        await _setup(hass, config_entry)
    add_extra_js_url.assert_called_once_with(
        hass, "/unifi_switch_ports/unifi-switch-ports-card.js?v=0.1.1"
    )
    notifications = persistent_notification._async_get_or_create_notifications(hass)
    assert RELOAD_NOTIFICATION_ID in notifications

    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": f"{DOMAIN}/subscribe"})
    assert (await client.receive_json())["success"]
    assert RELOAD_NOTIFICATION_ID not in notifications
