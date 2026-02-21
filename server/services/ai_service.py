import json
import logging
from collections.abc import AsyncIterator

import httpx

from exceptions import AIUnavailableError

logger = logging.getLogger(__name__)


class AIService:
    def __init__(self, base_url: str, api_key: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0))

    async def stream_completion(self, messages: list[dict]) -> AsyncIterator[str]:
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

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
            raise AIUnavailableError(f"Cannot reach AI provider: {exc}") from exc
        except httpx.TimeoutException as exc:
            raise AIUnavailableError(f"AI provider timed out: {exc}") from exc

    async def function_call(
        self, system_prompt: str, user_message: str, tools: list[dict]
    ) -> dict:
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

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
                    "tool_choice": {"type": "function", "function": {"name": "classify_intent"}},
                },
                headers=headers,
            )
            response.raise_for_status()
            return response.json()
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise AIUnavailableError(f"Cannot reach AI provider: {exc}") from exc
        except httpx.TimeoutException as exc:
            raise AIUnavailableError(f"AI provider timed out: {exc}") from exc

    async def health_check(self) -> bool:
        try:
            resp = await self.client.get(f"{self.base_url}/v1/models", timeout=5.0)
            return resp.status_code == 200
        except Exception:
            return False

    async def close(self):
        await self.client.aclose()
