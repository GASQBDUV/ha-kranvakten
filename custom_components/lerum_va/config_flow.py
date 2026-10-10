"""Konfigurationsflöde för Lerum VA."""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .api import EdpAuthError, EdpError, EdpFutureClient
from .const import (
    CONF_BASE_URL,
    CONF_CUSTOMER_ID,
    CONF_PERSONAL_NUMBER,
    DEFAULT_BASE_URL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


def _clean_pnr(value: str) -> str:
    return re.sub(r"\D", "", value or "")


class LerumVaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Hantera inställning via UI."""

    VERSION = 1

    async def _validate(self, data: dict[str, Any]) -> str | None:
        """Returnera felkod eller None om inloggningen fungerar."""
        if len(_clean_pnr(data[CONF_PERSONAL_NUMBER])) != 12:
            return "invalid_personal_number"
        client = EdpFutureClient(
            data.get(CONF_BASE_URL, DEFAULT_BASE_URL),
            data[CONF_CUSTOMER_ID],
            data[CONF_PERSONAL_NUMBER],
        )
        try:
            result = await client.async_fetch()
        except EdpAuthError:
            return "invalid_auth"
        except EdpError:
            _LOGGER.exception("Kunde inte nå portalen")
            return "cannot_connect"
        if not result.services:
            return "no_services"
        return None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input[CONF_CUSTOMER_ID] = str(user_input[CONF_CUSTOMER_ID]).strip()
            user_input[CONF_PERSONAL_NUMBER] = _clean_pnr(user_input[CONF_PERSONAL_NUMBER])
            user_input[CONF_BASE_URL] = user_input[CONF_BASE_URL].rstrip("/")
            await self.async_set_unique_id(
                f"{user_input[CONF_BASE_URL]}|{user_input[CONF_CUSTOMER_ID]}"
            )
            self._abort_if_unique_id_configured()
            if (error := await self._validate(user_input)) is None:
                return self.async_create_entry(
                    title=f"VA kund {user_input[CONF_CUSTOMER_ID]}", data=user_input
                )
            errors["base"] = error

        defaults = user_input or {}
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_CUSTOMER_ID, default=defaults.get(CONF_CUSTOMER_ID, "")
                ): str,
                vol.Required(
                    CONF_PERSONAL_NUMBER, default=defaults.get(CONF_PERSONAL_NUMBER, "")
                ): str,
                vol.Required(
                    CONF_BASE_URL, default=defaults.get(CONF_BASE_URL, DEFAULT_BASE_URL)
                ): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            data = {
                **entry.data,
                CONF_CUSTOMER_ID: str(user_input[CONF_CUSTOMER_ID]).strip(),
                CONF_PERSONAL_NUMBER: _clean_pnr(user_input[CONF_PERSONAL_NUMBER]),
            }
            if (error := await self._validate(data)) is None:
                return self.async_update_reload_and_abort(entry, data=data)
            errors["base"] = error

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_CUSTOMER_ID, default=entry.data.get(CONF_CUSTOMER_ID, "")
                ): str,
                vol.Required(CONF_PERSONAL_NUMBER): str,
            }
        )
        return self.async_show_form(
            step_id="reauth_confirm", data_schema=schema, errors=errors
        )
