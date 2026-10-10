"""DataUpdateCoordinator för Lerum VA."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import EdpAuthError, EdpData, EdpError, EdpFutureClient
from .const import (
    CONF_BASE_URL,
    CONF_CUSTOMER_ID,
    CONF_PERSONAL_NUMBER,
    DEFAULT_BASE_URL,
    DOMAIN,
    UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


class LerumVaCoordinator(DataUpdateCoordinator[EdpData]):
    """Hämtar data från portalen med jämna mellanrum."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.client = EdpFutureClient(
            entry.data.get(CONF_BASE_URL, DEFAULT_BASE_URL),
            entry.data[CONF_CUSTOMER_ID],
            entry.data[CONF_PERSONAL_NUMBER],
        )

    async def _async_update_data(self) -> EdpData:
        try:
            return await self.client.async_fetch()
        except EdpAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except EdpError as err:
            raise UpdateFailed(str(err)) from err
