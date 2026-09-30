"""Switch and port model built from the UniFi Network API responses."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from functools import cache
from pathlib import Path
from typing import Any

from .const import GATEWAY_TYPES, SWITCH_TYPES

# Rows of port numbers as seen from the front, None marks a gap.
type Layout = list[list[int | None]]

# Ports up to this count are drawn in one row by the fallback layout.
SINGLE_ROW_MAX_PORTS = 12


@cache
def model_table() -> dict[str, dict[str, Any]]:
    """
    Return model code -> {name, diagram, combo}.

    Generated from Ubiquiti's public device database by scripts/update_models.py.
    Loaded on first use; the integration module is imported in an executor.
    """
    return json.loads((Path(__file__).parent / "models.json").read_text())


@dataclass(slots=True)
class Neighbour:
    """Something connected to a port: a UniFi device or a client."""

    name: str
    detail: str = ""
    device: bool = False


@dataclass(slots=True)
class Port:
    """One switch port."""

    idx: int
    name: str
    media: str
    enabled: bool
    up: bool
    speed: int
    full_duplex: bool
    uplink: bool
    network: str | None
    tx_rate: float
    rx_rate: float
    poe_power: float
    poe: bool
    sfp_module: str | None
    combo: bool
    neighbours: list[Neighbour] = field(default_factory=list)

    @property
    def is_sfp(self) -> bool:
        """Return whether this is an SFP/QSFP cage."""
        return "SFP" in self.media.upper()


@dataclass(slots=True)
class Switch:
    """A UniFi switch or gateway with switch ports."""

    mac: str
    name: str
    model: str
    model_name: str
    gateway: bool
    online: bool
    ip: str | None
    version: str | None
    layout: Layout
    ports: list[Port]

    @property
    def ports_up(self) -> int:
        """Return the number of ports with link."""
        return sum(port.up for port in self.ports) if self.online else 0

    @property
    def poe_power(self) -> float:
        """Return the PoE power drawn by all ports in W."""
        return round(sum(port.poe_power for port in self.ports), 1)

    @property
    def has_poe(self) -> bool:
        """Return whether any port can supply PoE."""
        return any(port.poe for port in self.ports)

    def as_dict(self) -> dict[str, Any]:
        """Return the switch as the card consumes it."""
        data = asdict(self)
        data["ports_up"] = self.ports_up
        return data


def _number(value: Any) -> float:
    try:
        return float(value)
    except TypeError, ValueError:
        return 0.0


def parse_layout(diagram: list[str]) -> Layout:
    """Turn Ubiquiti's diagram rows ("01 02 __ 03") into port rows."""
    return [
        [int(token) if token.isdigit() else None for token in row.split()]
        for row in diagram
    ]


def fallback_layout(ports: list[Port]) -> Layout:
    """
    Guess a front view for models without a diagram.

    Copper ports first, SFP cages after a gap; above 12 ports odd numbers go
    into the top row and even numbers into the bottom row, like most rack
    switches.
    """
    copper = [p.idx for p in ports if not p.is_sfp]
    sfp = [p.idx for p in ports if p.is_sfp]
    if len(ports) <= SINGLE_ROW_MAX_PORTS:
        row: list[int | None] = list(copper)
        if sfp:
            row += [None, *sfp]
        return [row]
    top = copper[0::2] + ([None, *sfp[0::2]] if sfp else [])
    bottom = copper[1::2] + ([None, *sfp[1::2]] if sfp else [])
    return [top, bottom]


def _client_name(client: dict[str, Any]) -> str:
    return (
        client.get("name")
        or client.get("hostname")
        or client.get("ip")
        or client["mac"]
    )


def _client_detail(client: dict[str, Any]) -> str:
    parts = (client.get("ip"), client.get("mac"), client.get("network"))
    return " · ".join(p for p in parts if p)


def build_switches(
    devices: list[dict[str, Any]], clients: list[dict[str, Any]]
) -> dict[str, Switch]:
    """Build the switches of a site, keyed by MAC address."""
    models = model_table()
    device_by_mac = {d["mac"].lower(): d for d in devices if d.get("mac")}
    client_by_mac = {c["mac"].lower(): c for c in clients if c.get("mac")}
    clients_by_port: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for client in clients:
        if client.get("is_wired") and client.get("sw_mac") and client.get("sw_port"):
            key = (client["sw_mac"].lower(), client["sw_port"])
            clients_by_port.setdefault(key, []).append(client)

    def neighbours(switch_mac: str, port: dict[str, Any]) -> list[Neighbour]:
        """
        Return what is plugged into a port.

        A UniFi device (the controller's last connection / LLDP neighbour),
        else the wired clients the controller maps onto the port.
        """
        if not port.get("up"):
            return []
        last = port.get("last_connection") or {}
        last_mac = last.get("mac", "").lower() if last.get("connected") else ""
        if last_mac in device_by_mac:
            device = device_by_mac[last_mac]
            model = device.get("model", "")
            name = models.get(model, {}).get("name", model)
            detail = " · ".join(p for p in (name, device.get("ip")) if p)
            return [Neighbour(device.get("name") or last_mac, detail, device=True)]
        attached = clients_by_port.get((switch_mac, port.get("port_idx", 0)), [])
        if attached:
            return [Neighbour(_client_name(c), _client_detail(c)) for c in attached]
        if last_mac:
            client = client_by_mac.get(last_mac)
            if client:
                return [Neighbour(_client_name(client), _client_detail(client))]
            return [Neighbour(last_mac)]
        return []

    switches: dict[str, Switch] = {}
    for device in devices:
        if device.get("type") not in SWITCH_TYPES or not device.get("port_table"):
            continue
        mac = device["mac"].lower()
        model = device.get("model", "")
        info = models.get(model, {})
        combo_ports = {idx for pair in info.get("combo", []) for idx in pair}
        ports = [
            Port(
                idx=p["port_idx"],
                name=p.get("name") or f"Port {p['port_idx']}",
                media=p.get("media", ""),
                enabled=p.get("enable", p.get("enabled", True)) is not False
                and p.get("op_mode") != "disabled",
                up=bool(p.get("up")),
                speed=int(p.get("speed") or 0),
                full_duplex=bool(p.get("full_duplex")),
                uplink=bool(p.get("is_uplink")),
                network=p.get("network_name"),
                tx_rate=round(_number(p.get("tx_bytes-r"))),
                rx_rate=round(_number(p.get("rx_bytes-r"))),
                poe_power=round(_number(p.get("poe_power")), 1),
                poe=bool(p.get("port_poe")),
                sfp_module=p.get("sfp_part") if p.get("sfp_found") else None,
                combo=p["port_idx"] in combo_ports,
                neighbours=neighbours(mac, p),
            )
            for p in device["port_table"]
            if p.get("port_idx")
        ]
        ports.sort(key=lambda port: port.idx)
        known = {port.idx for port in ports}
        layout = parse_layout(info["diagram"]) if info.get("diagram") else []
        # Only trust the diagram if it covers exactly the reported ports.
        if {idx for row in layout for idx in row if idx is not None} != known:
            layout = fallback_layout(ports)
        switches[mac] = Switch(
            mac=mac,
            name=device.get("name") or mac,
            model=model,
            model_name=info.get("name", model),
            gateway=device.get("type") in GATEWAY_TYPES,
            online=device.get("state") == 1,
            ip=device.get("ip"),
            version=device.get("version"),
            layout=layout,
            ports=ports,
        )
    return switches
