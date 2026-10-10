"""Lerum VA – vattenförbrukning från EDP Future Webb."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import LerumVaCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]

type LerumVaConfigEntry = ConfigEntry[LerumVaCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: LerumVaConfigEntry) -> bool:
    """Sätt upp integrationen från en config entry."""
    coordinator = LerumVaCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: LerumVaConfigEntry) -> bool:
    """Ta bort integrationen."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
