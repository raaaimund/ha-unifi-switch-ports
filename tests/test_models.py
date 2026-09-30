"""Tests for the switch model."""

from __future__ import annotations

from custom_components.unifi_switch_ports.models import build_switches, parse_layout

from .conftest import load_fixture


def _switches() -> dict:
    return build_switches(
        load_fixture("stat_device.json")["data"], load_fixture("stat_sta.json")["data"]
    )


def test_parse_layout() -> None:
    """Ubiquiti's diagram rows become port rows with gaps."""
    assert parse_layout(["01 03 __ 05", "02 04 __ 06"]) == [
        [1, 3, None, 5],
        [2, 4, None, 6],
    ]


def test_only_switches() -> None:
    """Access points have no switch ports and are left out."""
    assert {s.name for s in _switches().values()} == {
        "UCG Fiber",
        "Office Switch",
        "Rack Switch",
        "US 8",
    }


def test_fallback_layout_without_diagram() -> None:
    """Models without a diagram get their ports in one row."""
    us8 = _switches()["aa:00:00:00:00:80"]
    assert us8.model_name == "US 8"
    assert us8.layout == [[1, 2, 3, 4, 5, 6, 7, 8]]
    assert us8.online is False
    assert us8.ports_up == 0


def test_neighbours() -> None:
    """Clients on a port, else the UniFi device behind it."""
    rack = _switches()["aa:00:00:00:00:75"]
    ports = {p.idx: p for p in rack.ports}
    assert [n.name for n in ports[1].neighbours] == ["nas"]
    assert [n.name for n in ports[8].neighbours] == ["server-1", "vm-1"]
    assert ports[4].neighbours[0].name == "Rack AP"
    assert ports[4].neighbours[0].device is True
    # Down ports have nothing connected.
    assert ports[5].neighbours == []
    assert ports[7].enabled is False


def test_totals() -> None:
    """Ports up and PoE power are summed per switch."""
    rack = _switches()["aa:00:00:00:00:75"]
    assert rack.ports_up == 6
    assert rack.poe_power == 26.5
    assert rack.has_poe is True
