"""Tests for serving and registering the Lovelace card."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from homeassistant.components import persistent_notification
from homeassistant.components.lovelace.const import LOVELACE_DATA
from homeassistant.setup import async_setup_component

from custom_components.unifi_switch_ports.const import DOMAIN, RELOAD_NOTIFICATION_ID

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from pytest_homeassistant_custom_component.typing import WebSocketGenerator

CARD = "/unifi_switch_ports/unifi-switch-ports-card.js"
VERSION = "0.1.3"


def _card_resources(hass: HomeAssistant) -> list[dict]:
    return [
        item
        for item in hass.data[LOVELACE_DATA].resources.async_items()
        if item["url"].startswith(CARD)
    ]


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.usefixtures("mock_api")
async def test_dashboard_resource(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    config_entry: MockConfigEntry,
) -> None:
    """The card becomes a dashboard resource; a running card clears the hint."""
    assert await async_setup_component(hass, "lovelace", {})
    await _setup(hass, config_entry)

    assert [(r["type"], r["url"]) for r in _card_resources(hass)] == [
        ("module", f"{CARD}?v={VERSION}")
    ]
    notifications = persistent_notification._async_get_or_create_notifications(hass)
    assert RELOAD_NOTIFICATION_ID in notifications

    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": f"{DOMAIN}/subscribe"})
    assert (await client.receive_json())["success"]
    assert RELOAD_NOTIFICATION_ID not in notifications

    # Removing the last entry removes the resource again.
    assert await hass.config_entries.async_remove(config_entry.entry_id)
    await hass.async_block_till_done()
    assert _card_resources(hass) == []


@pytest.mark.usefixtures("mock_api")
async def test_dashboard_resource_updated(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """An older version's resource is updated, duplicates are removed."""
    assert await async_setup_component(hass, "lovelace", {})
    resources = hass.data[LOVELACE_DATA].resources
    await resources.async_get_info()
    for version in ("0.1.0", "0.1.1"):
        await resources.async_create_item(
            {"res_type": "module", "url": f"{CARD}?v={version}"}
        )
    await resources.async_create_item({"res_type": "module", "url": "/local/other.js"})

    await _setup(hass, config_entry)
    urls = [r["url"] for r in resources.async_items()]
    assert urls == [f"{CARD}?v={VERSION}", "/local/other.js"]


@pytest.mark.usefixtures("mock_api")
async def test_extra_module_without_storage_resources(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """Without storage-mode resources the card is loaded as extra module."""
    hass.config.components.add("frontend")
    with patch(
        "homeassistant.components.frontend.add_extra_js_url"
    ) as add_extra_js_url:
        await _setup(hass, config_entry)
    add_extra_js_url.assert_called_once_with(hass, f"{CARD}?v={VERSION}")
