"""Exercise the real HTTP client using a local aiohttp endpoint."""

import asyncio
import sys
import unittest
from pathlib import Path

from aiohttp import ClientSession, web
from aiohttp.test_utils import TestServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from custom_components.nanobot_conversation.client import (
    NanobotAuthError,
    NanobotClient,
    NanobotError,
    normalize_url,
)


class ClientTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.requests = []
        self.status = 200
        self.invalid_json = False
        self.delay = 0
        self.models = {"data": [{"id": "configured-model"}]}
        self.response = {"choices": [{"message": {"content": "Bonjour."}}]}

        async def endpoint(request):
            self.requests.append(request)
            if self.delay:
                await asyncio.sleep(self.delay)
            self.assertEqual(request.headers["Authorization"], "Bearer private-test")
            if self.invalid_json:
                return web.Response(text="not json", content_type="application/json")
            if request.path == "/v1/models":
                data = self.models
            else:
                self.body = await request.json()
                data = self.response
            return web.json_response(data, status=self.status)

        app = web.Application()
        app.router.add_get("/v1/models", endpoint)
        app.router.add_post("/v1/chat/completions", endpoint)
        self.server = TestServer(app)
        await self.server.start_server()
        self.session = ClientSession()
        self.client = NanobotClient(self.session, str(self.server.make_url("/")), "private-test", 5)

    async def asyncTearDown(self):
        await self.session.close()
        await self.server.close()

    async def test_models_and_single_message_shape(self):
        await self.client.async_validate()
        text = await self.client.async_process('Bonjour "Maison"\n', "isolated-id")
        self.assertEqual(text, "Bonjour.")
        self.assertEqual(
            self.body,
            {
                "messages": [{"role": "user", "content": 'Bonjour "Maison"\n'}],
                "session_id": "isolated-id",
                "stream": False,
            },
        )
        self.assertNotIn("model", self.body)
        self.assertNotIn("tools", self.body)

    async def test_auth_error(self):
        for status in (401, 403):
            self.status = status
            with self.assertRaises(NanobotAuthError):
                await self.client.async_validate()

    async def test_http_error_no_retry(self):
        self.status = 503
        with self.assertRaisesRegex(NanobotError, "HTTP 503"):
            await self.client.async_process("Test", "one")
        self.assertEqual(len(self.requests), 1)

    async def test_invalid_json(self):
        self.invalid_json = True
        with self.assertRaises(NanobotError):
            await self.client.async_validate()

    async def test_invalid_model_list(self):
        for models in ({}, {"data": []}, {"data": [{"id": None}]}):
            self.models = models
            with self.assertRaises(NanobotError):
                await self.client.async_validate()

    async def test_timeout_is_error_without_retry(self):
        self.delay = 0.1
        client = NanobotClient(self.session, str(self.server.make_url("/")), "private-test", 0.01)
        with self.assertRaises(NanobotError):
            await client.async_validate()
        self.assertEqual(len(self.requests), 1)

    async def test_invalid_completion(self):
        for response in (
            {},
            {"choices": []},
            {"choices": [{"message": {"content": ""}}]},
            {"choices": [{"message": {"content": None}}]},
        ):
            self.response = response
            with self.assertRaises(NanobotError):
                await self.client.async_process("Test", "one")

    async def test_network_error(self):
        await self.server.close()
        with self.assertRaises(NanobotError):
            await self.client.async_validate()

    def test_url_normalization(self):
        self.assertEqual(normalize_url(" http://nanobot:8901/ "), "http://nanobot:8901/v1")
        self.assertEqual(normalize_url("https://nanobot/api/v1/"), "https://nanobot/api/v1")
        for url in (
            "file:///etc/passwd",
            "http://user:secret@nanobot",
            "http://nanobot?a=b",
            "http://nanobot/#fragment",
            "nanobot",
        ):
            with self.assertRaises(ValueError):
                normalize_url(url)


if __name__ == "__main__":
    unittest.main()
