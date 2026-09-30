"""Websocket API feeding the Lovelace card."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN, SIGNAL_UPDATE

if TYPE_CHECKING:
    from .data import UnifiSwitchPortsConfigEntry


@callback
def async_register_websocket_commands(hass: HomeAssistant) -> None:
    """Register the websocket commands."""
    websocket_api.async_register_command(hass, ws_subscribe)


def _entry(
    hass: HomeAssistant, entry_id: str | None
) -> UnifiSwitchPortsConfigEntry | None:
    """Return the requested entry, or the first one when none is given."""
    if entry_id:
        entry = hass.config_entries.async_get_entry(entry_id)
        return entry if entry and entry.domain == DOMAIN else None
    entries = hass.config_entries.async_entries(DOMAIN)
    loaded = [e for e in entries if e.state is ConfigEntryState.LOADED]
    return (loaded or entries or [None])[0]


def _payload(entry: UnifiSwitchPortsConfigEntry) -> dict[str, Any]:
    """Return the current data of an entry as sent to the card."""
    payload: dict[str, Any] = {
        "entry_id": entry.entry_id,
        "title": entry.title,
        "available": False,
        "updated": None,
        "switches": [],
    }
    if entry.state is not ConfigEntryState.LOADED:
        return payload
    coordinator = entry.runtime_data
    if coordinator.data is None:
        return payload
    switches = sorted(
        coordinator.data.switches.values(),
        key=lambda s: (not s.gateway, s.name.lower()),
    )
    payload["available"] = coordinator.last_update_success
    payload["updated"] = coordinator.data.updated.isoformat()
    payload["switches"] = [switch.as_dict() for switch in switches]
    return payload


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/subscribe",
        vol.Optional("entry_id"): str,
    }
)
@callback
def ws_subscribe(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Send the switches of a site now and after every update."""
    entry = _entry(hass, msg.get("entry_id"))
    if entry is None:
        connection.send_error(
            msg["id"], websocket_api.ERR_NOT_FOUND, "No UniFi Switch Ports entry found"
        )
        return
    entry_id = entry.entry_id

    @callback
    def send(updated_entry_id: str = entry_id) -> None:
        if updated_entry_id != entry_id:
            return
        # Looked up on every update so a reloaded entry keeps feeding the card.
        current = hass.config_entries.async_get_entry(entry_id)
        if current is not None:
            connection.send_message(
                websocket_api.event_message(msg["id"], _payload(current))
            )

    connection.subscriptions[msg["id"]] = async_dispatcher_connect(
        hass, SIGNAL_UPDATE, send
    )
    connection.send_result(msg["id"])
    send()
