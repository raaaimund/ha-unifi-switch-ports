"""Tests for diagnostics."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from homeassistant.components.diagnostics import REDACTED

from custom_components.unifi_switch_ports.diagnostics import (
    async_get_config_entry_diagnostics,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry


@pytest.mark.usefixtures("mock_api")
async def test_diagnostics_redacted(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """Secrets, addresses and names are redacted."""
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    diag = await async_get_config_entry_diagnostics(hass, config_entry)

    entry = diag["entry"]
    assert entry["title"] == REDACTED
    assert entry["data"]["api_key"] == REDACTED
    assert entry["data"]["url"] == REDACTED
    assert diag["switches"]
    for switch in diag["switches"]:
        assert switch["name"] == REDACTED
        assert switch["mac"] == REDACTED
        for port in switch["ports"]:
            assert port["name"] == REDACTED
            assert port["network"] in (None, REDACTED)
            for neighbour in port["neighbours"]:
                assert neighbour["name"] == REDACTED
                assert neighbour["detail"] == REDACTED
    assert any(port["neighbours"] for s in diag["switches"] for port in s["ports"])
