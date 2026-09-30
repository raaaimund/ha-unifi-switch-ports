#!/usr/bin/env python3
"""
Regenerate custom_components/unifi_switch_ports/models.json.

Reads Ubiquiti's public device database (the one the UniFi apps use) and keeps,
per switch/gateway model code, the product name and the front-panel port
diagram: rows of port numbers as seen from the front, "__" marks a gap.
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

SOURCE = "https://static.ui.com/fingerprint/ui/public.json"
TARGET = (
    Path(__file__).parent.parent / "custom_components/unifi_switch_ports/models.json"
)
TYPES = {"usw", "udm", "uxg", "ugw"}


def main() -> None:
    """Download the device database and write the trimmed model table."""
    with urllib.request.urlopen(SOURCE, timeout=60) as response:  # noqa: S310
        devices = json.load(response)["devices"]

    models: dict[str, dict] = {}
    for device in devices:
        network = device.get("unifi", {}).get("network", {})
        if network.get("type") not in TYPES:
            continue
        product = device.get("product", {})
        entry: dict = {"name": product.get("abbrev") or product.get("name")}
        if network.get("diagram"):
            entry["diagram"] = network["diagram"]
        meta = (network.get("ports") or {}).get("meta") or {}
        combos = [[int(p) for p in m["combo"]] for m in meta.values() if "combo" in m]
        if combos:
            entry["combo"] = combos
        for code in [network.get("model"), *device.get("shortnames", [])]:
            if code:
                models.setdefault(code, entry)

    TARGET.write_text(
        json.dumps(dict(sorted(models.items())), indent=1, ensure_ascii=False) + "\n"
    )
    print(f"{len(models)} model codes written to {TARGET}")  # noqa: T201


if __name__ == "__main__":
    main()
