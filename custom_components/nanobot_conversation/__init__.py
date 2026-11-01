"""Set up the Nanobot Conversation integration."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, CONF_URL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .client import NanobotAuthError, NanobotClient, NanobotError
from .const import CONF_TIMEOUT, DOMAIN

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
PLATFORMS = [Platform.CONVERSATION]
type NanobotConfigEntry = ConfigEntry[NanobotClient]


async def async_setup_entry(hass: HomeAssistant, entry: NanobotConfigEntry) -> bool:
    """Validate the endpoint and load the conversation entity."""
    client = NanobotClient(
        async_get_clientsession(hass),
        entry.data[CONF_URL],
        entry.data[CONF_API_KEY],
        entry.data[CONF_TIMEOUT],
    )
    try:
        await client.async_validate()
    except NanobotAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except NanobotError as err:
        raise ConfigEntryNotReady(str(err)) from err
    entry.runtime_data = client
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: NanobotConfigEntry) -> bool:
    """Unload without closing Home Assistant's shared HTTP session."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
