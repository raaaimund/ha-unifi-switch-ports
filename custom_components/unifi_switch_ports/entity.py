"""Base entity for UniFi Switch Ports."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import UnifiSwitchPortsCoordinator

if TYPE_CHECKING:
    from .models import Switch


class UnifiSwitchEntity(CoordinatorEntity[UnifiSwitchPortsCoordinator]):
    """An entity of one UniFi switch."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: UnifiSwitchPortsCoordinator, mac: str, key: str
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._mac = mac
        self._attr_unique_id = f"{mac}_{key}"
        self._attr_translation_key = key
        switch = self.switch
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, mac)},
            connections={(CONNECTION_NETWORK_MAC, mac)},
            manufacturer="Ubiquiti",
            model=switch.model_name,
            model_id=switch.model,
            name=switch.name,
            sw_version=switch.version,
        )

    @property
    def switch(self) -> Switch:
        """Return the switch of this entity."""
        return self.coordinator.data.switches[self._mac]

    @property
    def available(self) -> bool:
        """Return whether the switch is known and online."""
        return (
            super().available
            and self._mac in self.coordinator.data.switches
            and self.switch.online
        )
