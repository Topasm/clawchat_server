import logging
from collections.abc import AsyncIterator

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        self.active_connections[user_id] = websocket

    def disconnect(self, user_id: str):
        self.active_connections.pop(user_id, None)

    async def send_json(self, user_id: str, data: dict):
        ws = self.active_connections.get(user_id)
        if ws:
            try:
                await ws.send_json(data)
            except Exception:
                logger.warning("Failed to send WS message to %s, removing connection", user_id)
                self.disconnect(user_id)

    async def stream_to_user(
        self,
        user_id: str,
        message_id: str,
        conversation_id: str,
        token_iterator: AsyncIterator[str],
    ) -> str:
        await self.send_json(user_id, {
            "type": "stream_start",
            "data": {"message_id": message_id, "conversation_id": conversation_id},
        })

        full_content = ""
        index = 0
        async for token in token_iterator:
            full_content += token
            await self.send_json(user_id, {
                "type": "stream_chunk",
                "data": {"message_id": message_id, "content": token, "index": index},
            })
            index += 1

        await self.send_json(user_id, {
            "type": "stream_end",
            "data": {"message_id": message_id, "full_content": full_content},
        })

        return full_content


ws_manager = ConnectionManager()
