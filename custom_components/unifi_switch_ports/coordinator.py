"""DataUpdateCoordinator for UniFi Switch Ports."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.core import callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    UnifiApiAuthenticationError,
    UnifiApiError,
    UnifiApiSiteNotFoundError,
    UnifiNetworkClient,
)
from .const import CONF_SITE, DOMAIN, LOGGER, SIGNAL_UPDATE, UPDATE_INTERVAL
from .models import Switch, build_switches

if TYPE_CHECKING:
    from datetime import datetime

    from homeassistant.core import HomeAssistant

    from .data import UnifiSwitchPortsConfigEntry


@dataclass(slots=True)
class SiteData:
    """Switches of the site, keyed by MAC address."""

    switches: dict[str, Switch]
    updated: datetime


class UnifiSwitchPortsCoordinator(DataUpdateCoordinator[SiteData]):
    """Polls devices and clients of one UniFi site."""

    config_entry: UnifiSwitchPortsConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: UnifiSwitchPortsConfigEntry,
        client: UnifiNetworkClient,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.client = client
        self.site: str = entry.data[CONF_SITE]

    async def _async_update_data(self) -> SiteData:
        """Fetch devices and clients and build the switch model."""
        try:
            devices, clients = await asyncio.gather(
                self.client.async_get_devices(self.site),
                self.client.async_get_clients(self.site),
            )
        except UnifiApiAuthenticationError as err:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key="invalid_auth"
            ) from err
        except UnifiApiSiteNotFoundError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="site_not_found",
                translation_placeholders={"site": self.site},
            ) from err
        except UnifiApiError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        return SiteData(build_switches(devices, clients), dt_util.utcnow())

    @callback
    def async_update_listeners(self) -> None:
        """Update the entities and tell the card subscriptions."""
        super().async_update_listeners()
        async_dispatcher_send(self.hass, SIGNAL_UPDATE, self.config_entry.entry_id)
