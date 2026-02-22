import json
import logging
from collections.abc import AsyncIterator

import httpx

from exceptions import AIUnavailableError

logger = logging.getLogger(__name__)


class AIService:
    def __init__(self, base_url: str, api_key: str, model: str, provider: str = "openai"):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.provider = provider
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0))

    async def stream_completion(self, messages: list[dict]) -> AsyncIterator[str]:
        if self.provider == "ollama":
            async for token in self._stream_ollama(messages):
                yield token
        else:
            async for token in self._stream_openai(messages):
                yield token

    async def _stream_openai(self, messages: list[dict]) -> AsyncIterator[str]:
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

    async def _stream_ollama(self, messages: list[dict]) -> AsyncIterator[str]:
        try:
            async with self.client.stream(
                "POST",
                f"{self.base_url}/api/chat",
                json={"model": self.model, "messages": messages, "stream": True},
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                        if content := chunk.get("message", {}).get("content"):
                            yield content
                        if chunk.get("done"):
                            break
                    except json.JSONDecodeError:
                        continue
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise AIUnavailableError(f"Cannot reach AI provider: {exc}") from exc
        except httpx.TimeoutException as exc:
            raise AIUnavailableError(f"AI provider timed out: {exc}") from exc

    async def function_call(
        self,
        system_prompt: str,
        user_message: str,
        tools: list[dict],
        tool_choice: dict | str = "auto",
    ) -> dict:
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        # Use OpenAI-compatible endpoint (works for both OpenAI and Ollama)
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
            raise AIUnavailableError(f"Cannot reach AI provider: {exc}") from exc
        except httpx.TimeoutException as exc:
            raise AIUnavailableError(f"AI provider timed out: {exc}") from exc

    async def generate_title(self, user_message: str) -> str:
        """Generate a short conversation title from the first user message."""
        system = (
            "Generate a short title (max 6 words) for a conversation that starts with "
            "the following user message. Reply with ONLY the title, no quotes or punctuation "
            "at the start/end."
        )
        try:
            title = await self.generate_completion(system, user_message)
            # Trim to 60 chars max as safety net
            return title[:60] if title else "New Conversation"
        except Exception:
            logger.warning("Title generation failed, using fallback")
            return "New Conversation"

    async def generate_completion(self, system_prompt: str, user_message: str) -> str:
        """General-purpose non-streaming LLM call. Raises AIUnavailableError on failure."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        if self.provider == "ollama":
            url = f"{self.base_url}/api/chat"
            payload = {"model": self.model, "messages": messages, "stream": False}
        else:
            url = f"{self.base_url}/v1/chat/completions"
            payload = {"model": self.model, "messages": messages}

        try:
            resp = await self.client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

            if self.provider == "ollama":
                return data.get("message", {}).get("content", "").strip()
            else:
                return data["choices"][0]["message"]["content"].strip()
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise AIUnavailableError(f"Cannot reach AI provider: {exc}") from exc
        except httpx.TimeoutException as exc:
            raise AIUnavailableError(f"AI provider timed out: {exc}") from exc

    async def health_check(self) -> bool:
        try:
            if self.provider == "ollama":
                resp = await self.client.get(f"{self.base_url}/api/tags", timeout=5.0)
            else:
                resp = await self.client.get(f"{self.base_url}/v1/models", timeout=5.0)
            return resp.status_code == 200
        except Exception:
            return False

    async def close(self):
        await self.client.aclose()
