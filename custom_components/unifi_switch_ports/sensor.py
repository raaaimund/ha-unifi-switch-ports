"""Sensors of UniFi Switch Ports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfPower
from homeassistant.core import callback

from .entity import UnifiSwitchEntity

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from .coordinator import UnifiSwitchPortsCoordinator
    from .data import UnifiSwitchPortsConfigEntry
    from .models import Switch

# All data comes from the coordinator.
PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class UnifiSwitchSensorDescription(SensorEntityDescription):
    """Describes a switch sensor."""

    value_fn: Callable[[Switch], float | int]
    supported_fn: Callable[[Switch], bool] = lambda _switch: True


SENSORS: tuple[UnifiSwitchSensorDescription, ...] = (
    UnifiSwitchSensorDescription(
        key="ports_up",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda switch: switch.ports_up,
    ),
    UnifiSwitchSensorDescription(
        key="poe_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda switch: switch.poe_power,
        supported_fn=lambda switch: switch.has_poe,
    ),
)


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: UnifiSwitchPortsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors, and add them for switches adopted later."""
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def add_new_switches() -> None:
        new = set(coordinator.data.switches) - known
        if not new:
            return
        known.update(new)
        async_add_entities(
            UnifiSwitchSensor(coordinator, mac, description)
            for mac in new
            for description in SENSORS
            if description.supported_fn(coordinator.data.switches[mac])
        )

    add_new_switches()
    entry.async_on_unload(coordinator.async_add_listener(add_new_switches))


class UnifiSwitchSensor(UnifiSwitchEntity, SensorEntity):
    """A sensor of one UniFi switch."""

    entity_description: UnifiSwitchSensorDescription

    def __init__(
        self,
        coordinator: UnifiSwitchPortsCoordinator,
        mac: str,
        description: UnifiSwitchSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, mac, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | int:
        """Return the sensor value."""
        return self.entity_description.value_fn(self.switch)
