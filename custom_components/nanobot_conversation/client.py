"""Client for Nanobot's native OpenAI-compatible agent API."""

from typing import Any

import aiohttp
from yarl import URL


class NanobotError(Exception):
    """An unavailable or invalid Nanobot response."""


class NanobotAuthError(NanobotError):
    """The endpoint rejected authentication."""


def normalize_url(value: str) -> str:
    """Accept only a plain HTTP(S) base URL."""
    url = URL(value.strip())
    if (
        url.scheme not in {"http", "https"}
        or not url.host
        or url.user is not None
        or url.password is not None
        or url.query_string
        or url.fragment
    ):
        raise ValueError("Invalid Nanobot base URL")
    path = url.path.rstrip("/")
    if not path.endswith("/v1"):
        path += "/v1"
    return str(url.with_path(path))


class NanobotClient:
    """Use one shared Home Assistant HTTP session without retrying actions."""

    def __init__(
        self, session: aiohttp.ClientSession, url: str, api_key: str, timeout: float
    ) -> None:
        self._session = session
        self._url = normalize_url(url)
        self._api_key = api_key.strip()
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        if not self._api_key:
            raise ValueError("An API key is required")

    async def _request(self, method: str, path: str, data: dict[str, Any] | None = None) -> Any:
        try:
            async with self._session.request(
                method,
                self._url + path,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=data,
                timeout=self._timeout,
                allow_redirects=False,
            ) as response:
                if response.status in {401, 403}:
                    raise NanobotAuthError("Nanobot rejected authentication")
                if response.status != 200:
                    raise NanobotError(f"Nanobot returned HTTP {response.status}")
                return await response.json()
        except (TimeoutError, aiohttp.ClientError, ValueError) as err:
            raise NanobotError("Nanobot is unreachable or returned invalid JSON") from err

    async def async_validate(self) -> None:
        """Check the authenticated models endpoint without an LLM request."""
        data = await self._request("GET", "/models")
        if not isinstance(data, dict) or not isinstance(data.get("data"), list):
            raise NanobotError("Invalid Nanobot model list")
        if not any(
            isinstance(model, dict) and isinstance(model.get("id"), str) and model["id"]
            for model in data["data"]
        ):
            raise NanobotError("Nanobot has no configured model")

    async def async_process(self, text: str, session_id: str) -> str:
        """Send one user message, leaving model and tools under Nanobot's control."""
        data = await self._request(
            "POST",
            "/chat/completions",
            {
                "messages": [{"role": "user", "content": text}],
                "session_id": session_id,
                "stream": False,
            },
        )
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as err:
            raise NanobotError("Invalid Nanobot completion") from err
        if not isinstance(content, str) or not content.strip():
            raise NanobotError("Nanobot returned an empty completion")
        return content
