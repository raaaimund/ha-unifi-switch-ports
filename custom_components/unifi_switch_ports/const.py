"""Constants for the UniFi Switch Ports integration."""

from __future__ import annotations

from datetime import timedelta
from logging import Logger, getLogger

LOGGER: Logger = getLogger(__package__)

DOMAIN = "unifi_switch_ports"

CONF_SITE = "site"

# The UniFi controller refreshes the port rates about every 30 seconds.
UPDATE_INTERVAL = timedelta(seconds=30)

# Dispatcher signal sent after every coordinator update, with the entry id.
SIGNAL_UPDATE = f"{DOMAIN}_update"

# The Lovelace card, served by the integration and loaded into the frontend.
FRONTEND_URL_BASE = f"/{DOMAIN}"
CARD_FILENAME = "unifi-switch-ports-card.js"

# Persistent notification asking to reload the browser after the card was
# registered while Home Assistant was already running.
RELOAD_NOTIFICATION_ID = f"{DOMAIN}_reload_frontend"

# UniFi device types that have switch ports.
SWITCH_TYPES = frozenset({"usw", "udm", "uxg", "ugw"})
GATEWAY_TYPES = frozenset({"udm", "uxg", "ugw"})
