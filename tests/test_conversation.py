"""Test routing using Home Assistant's installed conversation contracts."""

import asyncio
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant import bootstrap, loader
from homeassistant.components import conversation
from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import intent

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from custom_components.nanobot_conversation.client import NanobotAuthError, NanobotError
from custom_components.nanobot_conversation.conversation import (
    NanobotConversationEntity,
    session_key,
)


class RoutingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = SimpleNamespace(async_process=AsyncMock(return_value="Réponse Maison."))
        self.entry = SimpleNamespace(
            entry_id="endpoint",
            data={"name": "Maison"},
            runtime_data=self.client,
            async_start_reauth=MagicMock(),
        )
        self.entity = NanobotConversationEntity(self.entry)
        self.entity.hass = MagicMock()
        response = intent.IntentResponse(language="fr")
        response.async_set_error(intent.IntentResponseErrorCode.NO_INTENT_MATCH, "Inconnu")
        self.local = conversation.ConversationResult(response=response, conversation_id="local")
        self.native = AsyncMock(return_value=self.local)
        self.patch = patch(
            "custom_components.nanobot_conversation.conversation.conversation.async_converse",
            self.native,
        )
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def input(self, user="parent", conversation_id="outer", device="device", satellite=None):
        return conversation.ConversationInput(
            text="donne moi la météo du jour",
            context=Context(user_id=user),
            conversation_id=conversation_id,
            device_id=device,
            satellite_id=satellite,
            language="fr",
            agent_id="conversation.maison",
        )

    async def test_fallback_codes(self):
        for code in ("no_intent_match", "no_valid_targets"):
            with self.subTest(code=code):
                self.local.response.error_code = intent.IntentResponseErrorCode(code)
                result = await self.entity.async_process(self.input())
                self.assertEqual(result.conversation_id, "outer")
                self.assertEqual(result.response.speech["plain"]["speech"], "Réponse Maison.")
                self.assertEqual(
                    self.native.call_args.kwargs["agent_id"], "conversation.home_assistant"
                )
                self.assertEqual(self.native.call_args.kwargs["device_id"], "device")
                self.assertTrue(self.client.async_process.call_args.args[1].startswith("ha-"))

    async def test_negative_answer_and_local_history_preserved(self):
        self.local.response = intent.IntentResponse(language="fr")
        self.local.response.async_set_speech("Non, la porte n'est pas ouverte.")
        self.local.continue_conversation = True
        result = await self.entity.async_process(self.input())
        self.assertIs(result.response, self.local.response)
        self.assertTrue(result.continue_conversation)
        self.client.async_process.assert_not_awaited()

    async def test_execution_errors_never_retried(self):
        for code in ("failed_to_handle", "unknown"):
            self.local.response.error_code = intent.IntentResponseErrorCode(code)
            result = await self.entity.async_process(self.input())
            self.assertIs(result.response, self.local.response)
        self.client.async_process.assert_not_awaited()

    async def test_native_failure_never_calls_nanobot(self):
        self.native.side_effect = HomeAssistantError("unavailable")
        with self.assertLogs("custom_components.nanobot_conversation.conversation", "ERROR"):
            result = await self.entity.async_process(self.input())
        self.assertEqual(result.response.response_type, intent.IntentResponseType.ERROR)
        self.client.async_process.assert_not_awaited()

    async def test_fallback_failure_is_not_success(self):
        self.client.async_process.side_effect = NanobotError("offline")
        with self.assertLogs("custom_components.nanobot_conversation.conversation", "WARNING"):
            result = await self.entity.async_process(self.input())
        self.assertEqual(result.response.response_type, intent.IntentResponseType.ERROR)
        self.assertIn("Aucune réussite", result.response.speech["plain"]["speech"])
        self.assertEqual(self.client.async_process.await_count, 1)

    async def test_auth_error_starts_reauth(self):
        self.client.async_process.side_effect = NanobotAuthError("rejected")
        with self.assertLogs("custom_components.nanobot_conversation.conversation", "WARNING"):
            result = await self.entity.async_process(self.input())
        self.entry.async_start_reauth.assert_called_once_with(self.entity.hass)
        self.assertEqual(result.response.response_type, intent.IntentResponseType.ERROR)

    async def test_cancellation_propagates_without_second_attempt(self):
        self.client.async_process.side_effect = asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            await self.entity.async_process(self.input())
        self.assertEqual(self.client.async_process.await_count, 1)

    async def test_conversation_continuity_and_new_session(self):
        first = await self.entity.async_process(self.input(conversation_id=None))
        first_key = self.client.async_process.call_args.args[1]
        second = await self.entity.async_process(self.input(conversation_id=first.conversation_id))
        self.assertEqual(first.conversation_id, second.conversation_id)
        self.assertEqual(first_key, self.client.async_process.call_args.args[1])
        await self.entity.async_process(self.input(conversation_id=None))
        self.assertNotEqual(first_key, self.client.async_process.call_args.args[1])

    def test_scope_isolation(self):
        original = self.input()
        base = session_key("endpoint", original, "outer")
        for changed in (
            self.input(user="child"),
            self.input(device="other"),
            self.input(satellite="kitchen"),
            self.input(user=None),
        ):
            self.assertNotEqual(base, session_key("endpoint", changed, "outer"))
        self.assertNotEqual(base, session_key("other", original, "outer"))
        self.assertNotEqual(base, session_key("endpoint", original, "another"))


class NativeAgentIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_actual_home_assistant_agent_local_and_fallback(self):
        hass = HomeAssistant("/tmp/nanobot-test")
        try:
            loader.async_setup(hass)
            Path(hass.config.config_dir).mkdir(parents=True, exist_ok=True)
            self.assertIsNotNone(
                await bootstrap.async_from_config_dict(
                    {
                        "homeassistant": {
                            "latitude": 47.0,
                            "longitude": 8.0,
                            "time_zone": "Europe/Zurich",
                            "country": "CH",
                        },
                        "conversation": {},
                    },
                    hass,
                )
            )
            self.assertIn("conversation", hass.config.components)
            client = SimpleNamespace(async_process=AsyncMock(return_value="Petite histoire."))
            with (
                patch(
                    "custom_components.nanobot_conversation.client.NanobotClient.async_validate",
                    AsyncMock(),
                ),
                patch(
                    "custom_components.nanobot_conversation.config_flow.async_get_clientsession",
                    return_value=MagicMock(),
                ),
                patch(
                    "custom_components.nanobot_conversation.async_get_clientsession",
                    return_value=MagicMock(),
                ),
            ):
                configured = await hass.config_entries.flow.async_init(
                    "nanobot_conversation",
                    context={"source": "user"},
                    data={
                        "name": "Maison",
                        "url": "http://nanobot:8901",
                        "api_key": "test-key",
                        "timeout": 65,
                    },
                )
                self.assertEqual(configured["type"], "create_entry")
                await hass.async_block_till_done()
            entry = configured["result"]
            entry.runtime_data = client
            entity = conversation.async_get_agent(hass, "conversation.maison")
            self.assertIsInstance(entity, NanobotConversationEntity)
            user_input = conversation.ConversationInput(
                text="quelle heure est-il",
                context=Context(),
                conversation_id=None,
                device_id=None,
                satellite_id=None,
                language="fr",
                agent_id="conversation.maison",
            )
            local = await conversation.async_converse(
                hass,
                text=user_input.text,
                conversation_id=None,
                context=user_input.context,
                language="fr",
                agent_id=entity.entity_id,
            )
            self.assertNotEqual(local.response.response_type, intent.IntentResponseType.ERROR)
            client.async_process.assert_not_awaited()
            fallback = await entity.async_process(
                replace(user_input, text="raconte une histoire courte")
            )
            self.assertEqual(fallback.response.speech["plain"]["speech"], "Petite histoire.")
            client.async_process.assert_awaited_once()
            self.assertTrue(await hass.config_entries.async_unload(entry.entry_id))
            self.assertIsNone(conversation.async_get_agent(hass, entity.entity_id))
        finally:
            await hass.async_stop(force=True)


if __name__ == "__main__":
    unittest.main()
