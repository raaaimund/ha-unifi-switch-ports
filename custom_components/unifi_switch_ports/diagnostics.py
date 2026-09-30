"""Diagnostics support for UniFi Switch Ports."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_API_KEY

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .data import UnifiSwitchPortsConfigEntry

TO_REDACT = {CONF_API_KEY}
# MAC and IP addresses of switches and of what is connected to their ports.
TO_REDACT_SWITCHES = {"mac", "ip", "detail"}


async def async_get_config_entry_diagnostics(
    _hass: HomeAssistant, entry: UnifiSwitchPortsConfigEntry
) -> dict[str, Any]:
    """Return diagnostics of a config entry."""
    coordinator = entry.runtime_data
    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "last_update_success": coordinator.last_update_success,
        "switches": [
            async_redact_data(switch.as_dict(), TO_REDACT_SWITCHES)
            for switch in coordinator.data.switches.values()
        ],
    }
