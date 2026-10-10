"""Sensorer för Lerum VA."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import LerumVaConfigEntry
from .api import Service
from .const import DOMAIN
from .coordinator import LerumVaCoordinator


@dataclass(frozen=True, kw_only=True)
class LerumVaSensorDescription(SensorEntityDescription):
    """Beskriver en sensor."""

    value_fn: Callable[[Service], Any]


SENSORS: tuple[LerumVaSensorDescription, ...] = (
    LerumVaSensorDescription(
        key="meter_reading",
        translation_key="meter_reading",
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        suggested_display_precision=1,
        value_fn=lambda s: s.last_reading,
    ),
    LerumVaSensorDescription(
        key="last_reading_date",
        translation_key="last_reading_date",
        device_class=SensorDeviceClass.DATE,
        value_fn=lambda s: s.last_reading_date,
    ),
    LerumVaSensorDescription(
        key="annual_consumption",
        translation_key="annual_consumption",
        device_class=SensorDeviceClass.WATER,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        suggested_display_precision=0,
        value_fn=lambda s: s.annual_consumption,
    ),
    LerumVaSensorDescription(
        key="estimated_annual_cost",
        translation_key="estimated_annual_cost",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement="SEK",
        suggested_display_precision=0,
        value_fn=lambda s: s.estimated_annual_cost,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LerumVaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Skapa sensorer för varje abonnemang."""
    coordinator = entry.runtime_data
    async_add_entities(
        LerumVaSensor(coordinator, service_id, description)
        for service_id in coordinator.data.services
        for description in SENSORS
    )


class LerumVaSensor(CoordinatorEntity[LerumVaCoordinator], SensorEntity):
    """En sensor för ett abonnemang."""

    _attr_has_entity_name = True
    entity_description: LerumVaSensorDescription

    def __init__(
        self,
        coordinator: LerumVaCoordinator,
        service_id: str,
        description: LerumVaSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._service_id = service_id
        entry_id = coordinator.config_entry.entry_id
        self._attr_unique_id = f"{entry_id}_{service_id}_{description.key}"
        service = coordinator.data.services[service_id]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_{service_id}")},
            name=f"Vattenmätare {service.building_name}".strip(),
            manufacturer="Lerums kommun VA",
            model="Vattenmätare (EDP Future)",
            serial_number=service.meter_number,
        )

    @property
    def _service(self) -> Service | None:
        return self.coordinator.data.services.get(self._service_id)

    @property
    def available(self) -> bool:
        return super().available and self._service is not None

    @property
    def native_value(self) -> Any:
        service = self._service
        return self.entity_description.value_fn(service) if service else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        service = self._service
        if service is None or self.entity_description.key != "meter_reading":
            return None
        return {
            "abonnemangsnummer": service.service_id,
            "matarnummer": service.meter_number,
            "senaste_avlasning": (
                service.last_reading_date.isoformat()
                if service.last_reading_date
                else None
            ),
        }
