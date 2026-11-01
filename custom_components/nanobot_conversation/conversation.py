"""Route through Home Assistant first, then Nanobot for unhandled requests."""

import hashlib
import logging
import uuid
from dataclasses import replace
from typing import Literal

from homeassistant.components import conversation
from homeassistant.const import CONF_NAME, MATCH_ALL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import intent
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import NanobotConfigEntry
from .client import NanobotAuthError, NanobotError
from .const import FALLBACK_CODES

_LOGGER = logging.getLogger(__name__)


def session_key(entry_id: str, user_input: conversation.ConversationInput, outer_id: str) -> str:
    """Separate histories by entry, authenticated user, device, satellite and conversation."""
    scope = "\0".join(
        (
            entry_id,
            user_input.context.user_id or "",
            user_input.device_id or "",
            user_input.satellite_id or "",
            outer_id,
        )
    )
    return hashlib.sha256(scope.encode()).hexdigest()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NanobotConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create one agent for the configured Nanobot endpoint."""
    async_add_entities([NanobotConversationEntity(entry)])


class NanobotConversationEntity(conversation.ConversationEntity):
    """A native conversation extension, not a replacement of the Assist pipeline."""

    _attr_supported_features = conversation.ConversationEntityFeature.CONTROL

    def __init__(self, entry: NanobotConfigEntry) -> None:
        self._entry = entry
        self._attr_name = entry.data[CONF_NAME]
        self._attr_unique_id = entry.entry_id

    @property
    def supported_languages(self) -> list[str] | Literal["*"]:
        return MATCH_ALL

    async def async_process(
        self, user_input: conversation.ConversationInput
    ) -> conversation.ConversationResult:
        """Preserve local results, including negative answers and execution errors."""
        outer_id = user_input.conversation_id or uuid.uuid4().hex
        key = session_key(self._entry.entry_id, user_input, outer_id)
        try:
            local = await conversation.async_converse(
                self.hass,
                text=user_input.text,
                conversation_id="nanobot-local-" + key,
                context=user_input.context,
                language=user_input.language,
                agent_id=conversation.HOME_ASSISTANT_AGENT,
                device_id=user_input.device_id,
                satellite_id=user_input.satellite_id,
                extra_system_prompt=user_input.extra_system_prompt,
            )
        except HomeAssistantError, ValueError:
            _LOGGER.exception("The native Home Assistant agent failed; Nanobot was not called")
            return self._error(user_input, outer_id, "Home Assistant is unavailable.")

        if (
            local.response.response_type != intent.IntentResponseType.ERROR
            or local.response.error_code not in FALLBACK_CODES
        ):
            return replace(local, conversation_id=outer_id)

        try:
            text = await self._entry.runtime_data.async_process(user_input.text, "ha-" + key)
        except NanobotAuthError as err:
            _LOGGER.warning("Nanobot authentication failed: %s", err)
            self._entry.async_start_reauth(self.hass)
            return self._error(user_input, outer_id, "Nanobot authentication is required.")
        except NanobotError as err:
            _LOGGER.warning("Nanobot fallback failed: %s", err)
            return self._error(
                user_input,
                outer_id,
                "Nanobot is unavailable. No successful action is confirmed.",
            )
        response = intent.IntentResponse(language=user_input.language)
        response.async_set_speech(text)
        return conversation.ConversationResult(response=response, conversation_id=outer_id)

    @staticmethod
    def _error(
        user_input: conversation.ConversationInput, outer_id: str, message: str
    ) -> conversation.ConversationResult:
        response = intent.IntentResponse(language=user_input.language)
        if user_input.language.startswith("fr"):
            message = {
                "Home Assistant is unavailable.": "Home Assistant est indisponible.",
                "Nanobot authentication is required.": (
                    "La connexion de Nanobot doit être renouvelée."
                ),
                "Nanobot is unavailable. No successful action is confirmed.": (
                    "Nanobot est indisponible. Aucune réussite n'est confirmée."
                ),
            }[message]
        response.async_set_error(intent.IntentResponseErrorCode.UNKNOWN, message)
        return conversation.ConversationResult(response=response, conversation_id=outer_id)
