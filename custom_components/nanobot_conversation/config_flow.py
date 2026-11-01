"""Configure and reconfigure a Nanobot endpoint using Home Assistant's UI."""

import logging
from typing import Any

import probatio
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_API_KEY, CONF_NAME, CONF_URL
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .client import NanobotAuthError, NanobotClient, NanobotError, normalize_url
from .const import CONF_TIMEOUT, DEFAULT_NAME, DEFAULT_TIMEOUT, DOMAIN

_LOGGER = logging.getLogger(__name__)


class NanobotConfigFlow(ConfigFlow, domain=DOMAIN):
    """Configure a Nanobot native agent API, without storing any model override."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._async_form("user", user_input)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._async_form("reconfigure", user_input)

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._async_form("reauth_confirm", user_input)

    async def _async_form(self, step: str, user_input: dict[str, Any] | None) -> ConfigFlowResult:
        entry = (
            self._get_reconfigure_entry()
            if step == "reconfigure"
            else self._get_reauth_entry()
            if step == "reauth_confirm"
            else None
        )
        defaults = (
            dict(entry.data)
            if entry
            else {CONF_NAME: DEFAULT_NAME, CONF_URL: "", CONF_TIMEOUT: DEFAULT_TIMEOUT}
        )
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                data = {
                    CONF_NAME: user_input[CONF_NAME].strip(),
                    CONF_URL: normalize_url(user_input[CONF_URL]),
                    CONF_API_KEY: user_input[CONF_API_KEY].strip(),
                    CONF_TIMEOUT: int(user_input[CONF_TIMEOUT]),
                }
                if (
                    not data[CONF_NAME]
                    or not data[CONF_API_KEY]
                    or not 5 <= data[CONF_TIMEOUT] <= 180
                ):
                    raise ValueError("Invalid settings")
            except ValueError, KeyError, TypeError:
                errors["base"] = "invalid_settings"
            else:
                client = NanobotClient(
                    async_get_clientsession(self.hass),
                    data[CONF_URL],
                    data[CONF_API_KEY],
                    data[CONF_TIMEOUT],
                )
                try:
                    await client.async_validate()
                except NanobotAuthError:
                    _LOGGER.warning("Nanobot endpoint rejected configuration authentication")
                    errors["base"] = "invalid_auth"
                except NanobotError as err:
                    _LOGGER.warning("Nanobot endpoint validation failed: %s", err)
                    errors["base"] = "cannot_connect"
                else:
                    if entry:
                        return self.async_update_reload_and_abort(
                            entry, title=data[CONF_NAME], data=data
                        )
                    self._async_abort_entries_match({CONF_URL: data[CONF_URL]})
                    return self.async_create_entry(title=data[CONF_NAME], data=data)
            defaults.update(
                {key: value for key, value in user_input.items() if key != CONF_API_KEY}
            )
        schema = probatio.Schema(
            {
                probatio.Required(CONF_NAME, default=defaults[CONF_NAME]): TextSelector(),
                probatio.Required(CONF_URL, default=defaults[CONF_URL]): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.URL)
                ),
                probatio.Required(CONF_API_KEY): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
                probatio.Required(CONF_TIMEOUT, default=defaults[CONF_TIMEOUT]): NumberSelector(
                    NumberSelectorConfig(min=5, max=180, step=1, mode=NumberSelectorMode.BOX)
                ),
            }
        )
        return self.async_show_form(step_id=step, data_schema=schema, errors=errors)
