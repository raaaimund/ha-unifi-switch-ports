"""
UniFi Switch Ports: the ports of all UniFi switches, as seen from the front.

Polls a UniFi Network controller with an API key, provides per-switch sensors
and serves the Lovelace card custom:unifi-switch-ports-card.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.const import CONF_API_KEY, CONF_URL, CONF_VERIFY_SSL, Platform
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.loader import async_get_integration

from .api import UnifiNetworkClient
from .const import CARD_FILENAME, DOMAIN, FRONTEND_URL_BASE
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
    """Serve the card and load it into every frontend session."""
    async_register_websocket_commands(hass)
    # frontend is an after-dependency: always there in a normal installation,
    # but not required to run the integration (e.g. in tests).
    if "frontend" not in hass.config.components:
        return True
    integration = await async_get_integration(hass, DOMAIN)
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                FRONTEND_URL_BASE,
                str(Path(__file__).parent / "frontend"),
                cache_headers=True,
            )
        ]
    )
    # The version query makes browsers fetch the card again after an update.
    add_extra_js_url(
        hass, f"{FRONTEND_URL_BASE}/{CARD_FILENAME}?v={integration.version}"
    )
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
