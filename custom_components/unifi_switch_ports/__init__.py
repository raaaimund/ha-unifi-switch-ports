"""
UniFi Switch Ports: the ports of all UniFi switches, as seen from the front.

Polls a UniFi Network controller with an API key, provides per-switch sensors
and serves the Lovelace card custom:unifi-switch-ports-card.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.const import CONF_API_KEY, CONF_URL, CONF_VERIFY_SSL, Platform
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.loader import async_get_integration

from .api import UnifiNetworkClient
from .card import async_register_card, async_unregister_card
from .const import DOMAIN
from .coordinator import UnifiSwitchPortsCoordinator
from .models import model_table
from .websocket import async_register_websocket_commands

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.typing import ConfigType

    from .data import UnifiSwitchPortsConfigEntry

PLATFORMS: list[Platform] = [Platform.SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, _config: ConfigType) -> bool:
    """Register the websocket API and the Lovelace card."""
    async_register_websocket_commands(hass)
    integration = await async_get_integration(hass, DOMAIN)
    await async_register_card(hass, str(integration.version))
    return True


async def async_setup_entry(
    hass: HomeAssistant, entry: UnifiSwitchPortsConfigEntry
) -> bool:
    """Set up a UniFi site from a config entry."""
    await hass.async_add_executor_job(model_table)
    client = UnifiNetworkClient(
        async_get_clientsession(hass, verify_ssl=entry.data[CONF_VERIFY_SSL]),
        entry.data[CONF_URL],
        entry.data[CONF_API_KEY],
    )
    coordinator = UnifiSwitchPortsCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: UnifiSwitchPortsConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(
    hass: HomeAssistant, entry: UnifiSwitchPortsConfigEntry
) -> None:
    """Remove the card's dashboard resource with the last entry."""
    others = [
        e
        for e in hass.config_entries.async_entries(DOMAIN)
        if e.entry_id != entry.entry_id
    ]
    if not others:
        await async_unregister_card(hass)
