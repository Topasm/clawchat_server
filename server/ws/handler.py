import asyncio
import logging

from fastapi import WebSocket, WebSocketDisconnect

from auth.jwt import decode_token
from exceptions import UnauthorizedError
from ws.manager import ws_manager

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 15  # seconds — keep connection alive through proxies


async def websocket_endpoint(websocket: WebSocket):
    # Authenticate via query param
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001, reason="Missing token")
        return

    try:
        payload = decode_token(token, expected_type="access")
        user_id = payload["sub"]
    except UnauthorizedError:
        await websocket.close(code=4001, reason="Invalid or expired token")
        return

    await ws_manager.connect(websocket, user_id)
    logger.info("WebSocket connected: %s", user_id)

    async def _heartbeat():
        """Send periodic heartbeat to keep the connection alive through proxies."""
        try:
            while True:
                await asyncio.sleep(HEARTBEAT_INTERVAL)
                await websocket.send_json({"type": "heartbeat"})
        except Exception:
            pass  # Connection closed; task will be cancelled

    heartbeat_task = asyncio.create_task(_heartbeat())

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
            elif msg_type == "typing":
                pass  # Typing indicators — no server action needed for single-user
            else:
                logger.warning("Unknown WS message type: %s", msg_type)
    except WebSocketDisconnect:
        ws_manager.disconnect(user_id)
        logger.info("WebSocket disconnected: %s", user_id)
    except Exception:
        ws_manager.disconnect(user_id)
        logger.exception("WebSocket error for user %s", user_id)
    finally:
        heartbeat_task.cancel()
