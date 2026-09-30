"""Client for the UniFi Network API, authenticated with an API key."""

from __future__ import annotations

import asyncio
import socket
from http import HTTPStatus
from typing import Any

import aiohttp

REQUEST_TIMEOUT = 20

# UniFi OS consoles (UDM, UCG, UniFi OS Server, ...) serve the Network API
# below /proxy/network, a standalone Network Application serves it at the root.
PATH_PREFIXES = ("/proxy/network", "")


class UnifiApiError(Exception):
    """General UniFi API error."""


class UnifiApiConnectionError(UnifiApiError):
    """The controller cannot be reached."""


class UnifiApiAuthenticationError(UnifiApiError):
    """The API key was rejected."""


class UnifiApiSiteNotFoundError(UnifiApiError):
    """The site does not exist on the controller."""


class UnifiNetworkClient:
    """Read-only client for the UniFi Network API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        url: str,
        api_key: str,
    ) -> None:
        """
        Initialize the client.

        TLS verification is configured on the session (verify_ssl of
        async_get_clientsession).
        """
        self._session = session
        self._url = url.rstrip("/")
        self._api_key = api_key
        self._prefix: str | None = None

    async def async_get_sites(self) -> list[dict[str, Any]]:
        """Return the sites the API key has access to."""
        return await self._request("/api/self/sites")

    async def async_get_devices(self, site: str) -> list[dict[str, Any]]:
        """Return all adopted devices of a site, including their port tables."""
        return await self._request(f"/api/s/{site}/stat/device")

    async def async_get_clients(self, site: str) -> list[dict[str, Any]]:
        """Return the currently connected clients of a site."""
        return await self._request(f"/api/s/{site}/stat/sta")

    async def _request(self, path: str) -> list[dict[str, Any]]:
        """GET a classic API endpoint and return its data list."""
        if self._prefix is not None:
            return await self._get(self._prefix + path)
        # Detect whether this is a UniFi OS console or a standalone application.
        for prefix in PATH_PREFIXES:
            try:
                data = await self._get(prefix + path)
            except _NotFoundError:
                continue
            self._prefix = prefix
            return data
        msg = f"No UniFi Network API found at {self._url}"
        raise UnifiApiConnectionError(msg)

    async def _get(self, path: str) -> list[dict[str, Any]]:
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                response = await self._session.get(
                    self._url + path,
                    headers={"X-API-KEY": self._api_key, "Accept": "application/json"},
                )
                if response.status == HTTPStatus.NOT_FOUND:
                    raise _NotFoundError
                body = await response.json(content_type=None)
        except TimeoutError as err:
            msg = f"Timeout connecting to {self._url}"
            raise UnifiApiConnectionError(msg) from err
        except (aiohttp.ClientError, socket.gaierror, ValueError) as err:
            msg = f"Error connecting to {self._url}: {err}"
            raise UnifiApiConnectionError(msg) from err

        meta = body.get("meta", {}) if isinstance(body, dict) else {}
        if meta.get("msg") == "api.err.NoSiteContext":
            msg = "Unknown site"
            raise UnifiApiSiteNotFoundError(msg)
        if response.status in (HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN):
            msg = "Invalid API key"
            raise UnifiApiAuthenticationError(msg)
        if response.status >= HTTPStatus.BAD_REQUEST or meta.get("rc") != "ok":
            msg = f"UniFi API error {response.status}: {meta.get('msg', body)}"
            raise UnifiApiError(msg)
        return body.get("data", [])


class _NotFoundError(Exception):
    """The endpoint does not exist below this path prefix."""
