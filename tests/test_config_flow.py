"""Tests for the config flow."""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING

import aiohttp
import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_API_KEY, CONF_URL, CONF_VERIFY_SSL
from homeassistant.data_entry_flow import FlowResultType

from custom_components.unifi_switch_ports.const import CONF_SITE, DOMAIN

from .conftest import API, ENTRY_DATA, SITE_ID, load_fixture

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from pytest_homeassistant_custom_component.test_util.aiohttp import (
        AiohttpClientMocker,
    )

USER_INPUT = {
    CONF_URL: "192.168.1.1/",
    CONF_API_KEY: "secret-key",
    CONF_VERIFY_SSL: False,
}


@pytest.mark.usefixtures("mock_api")
async def test_user_single_site(hass: HomeAssistant) -> None:
    """A key with one site creates the entry right away."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Default (192.168.1.1)"
    assert result["data"] == ENTRY_DATA
    assert result["result"].unique_id == SITE_ID


async def test_user_multiple_sites(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """With several sites the user picks one."""
    sites = load_fixture("self_sites.json")
    sites["data"].append({"_id": "abc", "name": "office", "desc": "Office"})
    aioclient_mock.get(f"{API}/self/sites", json=sites)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "site"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SITE: "office"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Office (192.168.1.1)"
    assert result["data"][CONF_SITE] == "office"
    assert result["result"].unique_id == "abc"


async def test_user_invalid_auth_then_recover(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A rejected key shows an error; a good one then succeeds."""
    aioclient_mock.get(
        f"{API}/self/sites",
        status=HTTPStatus.UNAUTHORIZED,
        json={"error": {"code": 401, "message": "Unauthorized"}},
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}

    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{API}/self/sites", json=load_fixture("self_sites.json"))
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_cannot_connect(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """An unreachable controller shows an error."""
    aioclient_mock.get(f"{API}/self/sites", exc=aiohttp.ClientConnectionError)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["errors"] == {"base": "cannot_connect"}


@pytest.mark.usefixtures("mock_api")
async def test_user_already_configured(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """The same site cannot be added twice."""
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.usefixtures("mock_api")
async def test_reauth(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    """A new API key replaces the rejected one."""
    config_entry.add_to_hass(hass)
    result = await config_entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "new-key"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert config_entry.data[CONF_API_KEY] == "new-key"
    # The flow reloaded the entry; stop its polling again.
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(config_entry.entry_id)


@pytest.mark.usefixtures("mock_api")
async def test_reconfigure(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    """The connection can be changed for the same controller."""
    config_entry.add_to_hass(hass)
    result = await config_entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**USER_INPUT, CONF_API_KEY: "other-key"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert config_entry.data[CONF_API_KEY] == "other-key"


async def test_reconfigure_wrong_controller(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> None:
    """Pointing the entry at another controller is refused."""
    sites = load_fixture("self_sites.json")
    sites["data"][0]["external_id"] = "another-controller"
    aioclient_mock.get(f"{API}/self/sites", json=sites)
    config_entry.add_to_hass(hass)
    result = await config_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_controller"
