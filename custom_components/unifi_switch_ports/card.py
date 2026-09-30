"""Serve the Lovelace card and make the dashboards load it."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from homeassistant.components import persistent_notification
from homeassistant.components.http import StaticPathConfig
from homeassistant.components.lovelace.const import LOVELACE_DATA, MODE_STORAGE

from .const import (
    CARD_FILENAME,
    FRONTEND_URL_BASE,
    LOGGER,
    RELOAD_NOTIFICATION_ID,
)

if TYPE_CHECKING:
    from homeassistant.components.lovelace.resources import (
        ResourceStorageCollection,
    )
    from homeassistant.core import HomeAssistant

CARD_URL = f"{FRONTEND_URL_BASE}/{CARD_FILENAME}"


async def async_register_card(hass: HomeAssistant, version: str) -> None:
    """
    Serve the card and register it with the frontend.

    With dashboards in storage mode the card becomes a dashboard resource:
    dashboards fetch their resources over the websocket on every load. An
    extra module URL is part of the HTML page instead, which the frontend's
    service worker serves stale from its cache, e.g. a copy fetched while Home
    Assistant was still starting and the card was not registered yet.
    """
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
    url = f"{CARD_URL}?v={version}"

    lovelace = hass.data.get(LOVELACE_DATA)
    if lovelace is not None and lovelace.resource_mode == MODE_STORAGE:
        changed = await _async_ensure_resource(lovelace.resources, url)
    elif "frontend" in hass.config.components:
        # Resources in YAML mode: fall back to an extra module URL.
        from homeassistant.components.frontend import add_extra_js_url  # noqa: PLC0415

        add_extra_js_url(hass, url)
        changed = True
    else:
        return

    if changed and hass.is_running:
        # Open browser tabs load resources only on a page load. The card's
        # first subscription dismisses this again (see websocket.py).
        persistent_notification.async_create(
            hass,
            "The **UniFi Switch Ports** card was added or updated. Reload Home "
            "Assistant in your browser to use it. In the companion app, reset "
            "the frontend cache in the app settings.",
            title="UniFi Switch Ports: reload the browser",
            notification_id=RELOAD_NOTIFICATION_ID,
        )


async def _async_ensure_resource(
    resources: ResourceStorageCollection, url: str
) -> bool:
    """Create or update the card's dashboard resource; return if it changed."""
    await resources.async_get_info()  # loads the collection
    ours = [
        item for item in resources.async_items() if item["url"].startswith(CARD_URL)
    ]
    if ours and ours[0]["url"] == url and len(ours) == 1:
        return False
    for duplicate in ours[1:]:
        await resources.async_delete_item(duplicate["id"])
    if ours:
        LOGGER.debug("Updating dashboard resource to %s", url)
        await resources.async_update_item(
            ours[0]["id"], {"res_type": "module", "url": url}
        )
    else:
        LOGGER.debug("Adding dashboard resource %s", url)
        await resources.async_create_item({"res_type": "module", "url": url})
    return True


async def async_unregister_card(hass: HomeAssistant) -> None:
    """Remove the card's dashboard resource."""
    lovelace = hass.data.get(LOVELACE_DATA)
    if lovelace is None or lovelace.resource_mode != MODE_STORAGE:
        return
    resources = lovelace.resources
    await resources.async_get_info()
    for item in list(resources.async_items()):
        if item["url"].startswith(CARD_URL):
            await resources.async_delete_item(item["id"])
