"""Check forms, validation and reload behavior without production access."""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import HomeAssistant

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from custom_components.nanobot_conversation.client import NanobotAuthError, NanobotError
from custom_components.nanobot_conversation.config_flow import NanobotConfigFlow


class ConfigFlowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.hass = HomeAssistant("/tmp/nanobot-flow-test")
        self.flow = NanobotConfigFlow()
        self.flow.hass = self.hass
        self.flow.context = {}
        self.data = {
            "name": "Maison",
            "url": "http://nanobot:8901",
            "api_key": "test-secret",
            "timeout": 65,
        }
        self.validation = AsyncMock()
        self.patch = patch(
            "custom_components.nanobot_conversation.config_flow.NanobotClient.async_validate",
            self.validation,
        )
        self.patch.start()
        self.addCleanup(self.patch.stop)
        session_patch = patch(
            "custom_components.nanobot_conversation.config_flow.async_get_clientsession",
            return_value=MagicMock(),
        )
        session_patch.start()
        self.addCleanup(session_patch.stop)

    async def asyncTearDown(self):
        await self.hass.async_stop(force=True)

    async def test_show_form(self):
        result = await self.flow.async_step_user()
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["step_id"], "user")

    async def test_create_entry(self):
        with patch.object(self.flow, "_async_abort_entries_match"):
            result = await self.flow.async_step_user(self.data)
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["data"]["url"], "http://nanobot:8901/v1")
        self.assertEqual(result["data"]["name"], "Maison")

    async def test_errors_do_not_return_success(self):
        for error, expected in (
            (NanobotAuthError("bad key"), "invalid_auth"),
            (NanobotError("offline"), "cannot_connect"),
        ):
            self.validation.side_effect = error
            with self.assertLogs("custom_components.nanobot_conversation.config_flow", "WARNING"):
                result = await self.flow.async_step_user(self.data)
            self.assertEqual(result["type"], "form")
            self.assertEqual(result["errors"]["base"], expected)

    async def test_invalid_settings(self):
        for change in ({"api_key": ""}, {"url": "file:///x"}, {"timeout": 0}, {"name": " "}):
            result = await self.flow.async_step_user(self.data | change)
            self.assertEqual(result["errors"]["base"], "invalid_settings")

    async def test_reconfigure_and_reauth_reload(self):
        entry = SimpleNamespace(data=self.data)
        for step, method in (
            ("reconfigure", "_get_reconfigure_entry"),
            ("reauth_confirm", "_get_reauth_entry"),
        ):
            with (
                patch.object(self.flow, method, return_value=entry),
                patch.object(
                    self.flow, "async_update_reload_and_abort", return_value={"type": "abort"}
                ) as update,
            ):
                result = await self.flow._async_form(step, self.data)
                self.assertEqual(result["type"], "abort")
                update.assert_called_once()
                self.assertEqual(update.call_args.kwargs["title"], "Maison")


if __name__ == "__main__":
    unittest.main()
