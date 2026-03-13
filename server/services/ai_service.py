"""AI Service — thin relay to OpenClaw (OpenAI-compatible gateway).

ClawChat Server does NOT handle LLM routing or API keys.
All AI work is delegated to OpenClaw via its /v1/chat/completions endpoint.
"""

import json
import logging
from collections.abc import AsyncIterator

import httpx

from exceptions import AIUnavailableError

logger = logging.getLogger(__name__)


class AIService:
    """Relay AI requests to OpenClaw's OpenAI-compatible API."""

    def __init__(self, base_url: str, api_key: str = "", model: str = "openclaw"):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0))

    # --- Streaming chat completion ---

    async def stream_completion(self, messages: list[dict]) -> AsyncIterator[str]:
        headers = self._auth_headers()

        try:
            async with self.client.stream(
                "POST",
                f"{self.base_url}/v1/chat/completions",
                json={"model": self.model, "messages": messages, "stream": True},
                headers=headers,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    payload = line[6:]
                    if payload.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(payload)
                        delta = chunk["choices"][0]["delta"]
                        if content := delta.get("content"):
                            yield content
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise AIUnavailableError(f"Cannot reach OpenClaw: {exc}") from exc
        except httpx.TimeoutException as exc:
            raise AIUnavailableError(f"OpenClaw timed out: {exc}") from exc

    # --- Function / tool calling ---

    async def function_call(
        self,
        system_prompt: str,
        user_message: str,
        tools: list[dict],
        tool_choice: dict | str = "auto",
    ) -> dict:
        headers = self._auth_headers()

        try:
            response = await self.client.post(
                f"{self.base_url}/v1/chat/completions",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    "tools": tools,
                    "tool_choice": tool_choice,
                },
                headers=headers,
            )
            response.raise_for_status()
            return response.json()
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise AIUnavailableError(f"Cannot reach OpenClaw: {exc}") from exc
        except httpx.TimeoutException as exc:
            raise AIUnavailableError(f"OpenClaw timed out: {exc}") from exc

    # --- Title generation ---

    async def generate_title(self, user_message: str) -> str:
        """Generate a short conversation title from the first user message."""
        system = (
            "Generate a short title (max 6 words) for a conversation that starts with "
            "the following user message. Reply with ONLY the title, no quotes or punctuation "
            "at the start/end."
        )
        try:
            title = await self.generate_completion(system, user_message)
            return title[:60] if title else "New Conversation"
        except Exception:
            logger.warning("Title generation failed, using fallback")
            return "New Conversation"

    # --- Non-streaming completion ---

    async def generate_completion(self, system_prompt: str, user_message: str) -> str:
        """General-purpose non-streaming LLM call via OpenClaw."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        headers = self._auth_headers()

        try:
            resp = await self.client.post(
                f"{self.base_url}/v1/chat/completions",
                json={"model": self.model, "messages": messages},
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise AIUnavailableError(f"Cannot reach OpenClaw: {exc}") from exc
        except httpx.TimeoutException as exc:
            raise AIUnavailableError(f"OpenClaw timed out: {exc}") from exc

    # --- Health check ---

    async def health_check(self) -> bool:
        try:
            resp = await self.client.get(
                f"{self.base_url}/v1/models",
                headers=self._auth_headers(),
                timeout=5.0,
            )
            content_type = resp.headers.get("content-type", "").lower()
            if resp.status_code == 200 and "application/json" in content_type:
                return True
        except Exception:
            pass

        # OpenClaw can expose chat completions without a /v1/models catalog.
        # A 405 here confirms the endpoint exists and auth succeeded.
        try:
            resp = await self.client.get(
                f"{self.base_url}/v1/chat/completions",
                headers=self._auth_headers(),
                timeout=5.0,
            )
            return resp.status_code == 405
        except Exception:
            return False

    async def close(self):
        await self.client.aclose()

    # --- Internal helpers ---

    def _auth_headers(self) -> dict:
        headers: dict[str, str] = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers
