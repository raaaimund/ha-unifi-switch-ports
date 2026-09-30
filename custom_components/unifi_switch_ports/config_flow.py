"""Config flow for UniFi Switch Ports."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_API_KEY, CONF_URL, CONF_VERIFY_SSL
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    UnifiApiAuthenticationError,
    UnifiApiConnectionError,
    UnifiApiError,
    UnifiNetworkClient,
)
from .const import CONF_SITE, DOMAIN, LOGGER

if TYPE_CHECKING:
    from collections.abc import Mapping

DEFAULT_URL = "https://192.168.1.1"

API_KEY_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


def _connection_schema(defaults: Mapping[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_URL, default=defaults.get(CONF_URL, DEFAULT_URL)
            ): TextSelector(TextSelectorConfig(type=TextSelectorType.URL)),
            vol.Required(CONF_API_KEY): API_KEY_SELECTOR,
            # UniFi consoles ship with a self-signed certificate.
            vol.Required(
                CONF_VERIFY_SSL, default=defaults.get(CONF_VERIFY_SSL, False)
            ): BooleanSelector(),
        }
    )


def _without_api_key(data: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return form defaults; the API key is never sent back to the frontend."""
    return {k: v for k, v in (data or {}).items() if k != CONF_API_KEY}


def _normalize_url(url: str) -> str:
    url = url.strip().rstrip("/")
    return url if "://" in url else f"https://{url}"


def _site_id(site: dict[str, Any]) -> str:
    """Return the stable id of a site (unique id of the config entry)."""
    return site.get("external_id") or site["_id"]


def _site_title(site: dict[str, Any], url: str) -> str:
    return f"{site.get('desc') or site['name']} ({urlparse(url).hostname})"


class UnifiSwitchPortsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for UniFi Switch Ports."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._data: dict[str, Any] = {}
        self._sites: dict[str, dict[str, Any]] = {}

    async def _async_get_sites(
        self, data: Mapping[str, Any]
    ) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
        """Connect with the given settings and return (sites by name, errors)."""
        client = UnifiNetworkClient(
            async_get_clientsession(self.hass, verify_ssl=data[CONF_VERIFY_SSL]),
            data[CONF_URL],
            data[CONF_API_KEY],
        )
        try:
            sites = await client.async_get_sites()
        except UnifiApiAuthenticationError:
            return {}, {"base": "invalid_auth"}
        except UnifiApiConnectionError:
            return {}, {"base": "cannot_connect"}
        except UnifiApiError:
            LOGGER.exception("Unexpected response from the UniFi controller")
            return {}, {"base": "unknown"}
        if not sites:
            return {}, {"base": "no_sites"}
        return {site["name"]: site for site in sites}, {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the controller and API key."""
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input[CONF_URL] = _normalize_url(user_input[CONF_URL])
            self._sites, errors = await self._async_get_sites(user_input)
            if not errors:
                self._data = user_input
                if len(self._sites) == 1:
                    return await self._async_create_site_entry(
                        next(iter(self._sites.values()))
                    )
                return await self.async_step_site()
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                _connection_schema(_without_api_key(user_input)),
                _without_api_key(user_input),
            ),
            errors=errors,
        )

    async def async_step_site(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user pick a site when the API key has access to several."""
        if user_input is not None:
            return await self._async_create_site_entry(
                self._sites[user_input[CONF_SITE]]
            )
        options = [
            SelectOptionDict(value=name, label=site.get("desc") or name)
            for name, site in self._sites.items()
        ]
        return self.async_show_form(
            step_id="site",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SITE): SelectSelector(
                        SelectSelectorConfig(
                            options=options, mode=SelectSelectorMode.DROPDOWN
                        )
                    )
                }
            ),
        )

    async def _async_create_site_entry(self, site: dict[str, Any]) -> ConfigFlowResult:
        await self.async_set_unique_id(_site_id(site))
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=_site_title(site, self._data[CONF_URL]),
            data={**self._data, CONF_SITE: site["name"]},
        )

    async def async_step_reauth(
        self, _entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle a rejected API key."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a new API key."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {**entry.data, CONF_API_KEY: user_input[CONF_API_KEY]}
            sites, errors = await self._async_get_sites(data)
            if not errors:
                if entry.data[CONF_SITE] not in sites:
                    return self.async_abort(reason="site_not_found")
                return self.async_update_reload_and_abort(entry, data=data)
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_API_KEY): API_KEY_SELECTOR}),
            description_placeholders={"url": entry.data[CONF_URL]},
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the controller URL, API key or TLS verification."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input[CONF_URL] = _normalize_url(user_input[CONF_URL])
            sites, errors = await self._async_get_sites(user_input)
            if not errors:
                site = sites.get(entry.data[CONF_SITE])
                if site is None:
                    return self.async_abort(reason="site_not_found")
                await self.async_set_unique_id(_site_id(site))
                self._abort_if_unique_id_mismatch(reason="wrong_controller")
                return self.async_update_reload_and_abort(
                    entry, data_updates=user_input
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                _connection_schema(entry.data),
                _without_api_key(user_input or entry.data),
            ),
            errors=errors,
        )
