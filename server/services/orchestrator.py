import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from exceptions import AIUnavailableError
from models.conversation import Conversation
from models.message import Message
from services.ai_service import AIService
from services.intent_classifier import classify_intent
from utils import make_id
from ws.manager import ConnectionManager

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are ClawChat, a helpful and friendly AI personal assistant.
You help the user manage their tasks, calendar, notes, and answer general questions.
Be concise but thorough. Use a warm, professional tone."""

# Intents that map to module stubs
MODULE_INTENTS = {
    "create_todo": "create a todo",
    "query_todos": "list your todos",
    "update_todo": "update a todo",
    "delete_todo": "delete a todo",
    "complete_todo": "complete a todo",
    "create_event": "create a calendar event",
    "query_events": "check your calendar",
    "update_event": "update a calendar event",
    "delete_event": "delete a calendar event",
    "create_memo": "create a memo",
    "query_memos": "search your memos",
    "update_memo": "update a memo",
    "delete_memo": "delete a memo",
}


class Orchestrator:
    def __init__(
        self,
        ai_service: AIService,
        ws_manager: ConnectionManager,
        session_factory: async_sessionmaker[AsyncSession],
    ):
        self.ai = ai_service
        self.ws = ws_manager
        self.session_factory = session_factory

    async def handle_message(
        self,
        user_id: str,
        conversation_id: str,
        message_id: str,
        content: str,
    ):
        async with self.session_factory() as db:
            try:
                # 1. Classify intent
                intent_result = await classify_intent(content, self.ai)
                intent = intent_result.intent
                params = intent_result.params

                # Update user message with classified intent
                user_msg = await db.get(Message, message_id)
                if user_msg:
                    user_msg.intent = intent

                # 2. Route based on intent
                if intent == "general_chat":
                    await self._handle_general_chat(
                        db, user_id, conversation_id, content
                    )
                elif intent in MODULE_INTENTS:
                    await self._handle_module_stub(
                        db, user_id, conversation_id, intent, params
                    )
                elif intent == "search":
                    query = params.get("query", content)
                    await self._send_stub_message(
                        db,
                        user_id,
                        conversation_id,
                        intent,
                        f"I'd search for '{query}' across all your data. Search module coming soon!",
                    )
                elif intent == "delegate_task":
                    await self._send_stub_message(
                        db,
                        user_id,
                        conversation_id,
                        intent,
                        "I'd delegate this as an async agent task. Agent tasks coming soon!",
                    )
                elif intent == "daily_briefing":
                    await self._send_stub_message(
                        db,
                        user_id,
                        conversation_id,
                        intent,
                        "I'd prepare your daily briefing here. Briefing module coming soon!",
                    )
                else:
                    # Fallback to general chat
                    await self._handle_general_chat(
                        db, user_id, conversation_id, content
                    )

                await db.commit()

            except AIUnavailableError as exc:
                logger.error("AI unavailable: %s", exc)
                await self._send_error_message(
                    db, user_id, conversation_id,
                    "I'm sorry, I can't reach the AI provider right now. Please check that your AI service is running.",
                )
                await db.commit()
            except Exception:
                logger.exception("Orchestrator error")
                await self._send_error_message(
                    db, user_id, conversation_id,
                    "Something went wrong processing your message. Please try again.",
                )
                await db.commit()

    async def _handle_general_chat(
        self,
        db: AsyncSession,
        user_id: str,
        conversation_id: str,
        content: str,
    ):
        # Load last 20 messages for context
        q = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(20)
        )
        rows = (await db.execute(q)).scalars().all()
        history = list(reversed(rows))

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        for msg in history:
            messages.append({"role": msg.role, "content": msg.content})

        # Create assistant message placeholder
        assistant_msg_id = make_id("msg_")

        # Stream response via WebSocket
        try:
            full_content = await self.ws.stream_to_user(
                user_id=user_id,
                message_id=assistant_msg_id,
                conversation_id=conversation_id,
                token_iterator=self.ai.stream_completion(messages),
            )
        except Exception:
            # Send stream_end for the orphaned stream_start so the client doesn't hang
            await self.ws.send_json(user_id, {
                "type": "stream_end",
                "data": {"message_id": assistant_msg_id, "full_content": ""},
            })
            raise

        # Save assistant message
        assistant_msg = Message(
            id=assistant_msg_id,
            conversation_id=conversation_id,
            role="assistant",
            content=full_content,
            intent="general_chat",
        )
        db.add(assistant_msg)

        # Update conversation timestamp
        conv = await db.get(Conversation, conversation_id)
        if conv:
            conv.updated_at = datetime.now(timezone.utc)

    async def _handle_module_stub(
        self,
        db: AsyncSession,
        user_id: str,
        conversation_id: str,
        intent: str,
        params: dict,
    ):
        action = MODULE_INTENTS[intent]
        title = params.get("title", "")
        detail = f": '{title}'" if title else ""

        response_text = (
            f"I understood you want to {action}{detail}. "
            f"This module is coming soon! For now, I've noted your intent."
        )

        await self._send_stub_message(db, user_id, conversation_id, intent, response_text)

    async def _send_stub_message(
        self,
        db: AsyncSession,
        user_id: str,
        conversation_id: str,
        intent: str,
        text: str,
    ):
        msg_id = make_id("msg_")
        msg = Message(
            id=msg_id,
            conversation_id=conversation_id,
            role="assistant",
            content=text,
            intent=intent,
        )
        db.add(msg)

        conv = await db.get(Conversation, conversation_id)
        if conv:
            conv.updated_at = datetime.now(timezone.utc)

        await self.ws.send_json(user_id, {
            "type": "stream_start",
            "data": {"message_id": msg_id, "conversation_id": conversation_id},
        })
        await self.ws.send_json(user_id, {
            "type": "stream_chunk",
            "data": {"message_id": msg_id, "content": text, "index": 0},
        })
        await self.ws.send_json(user_id, {
            "type": "stream_end",
            "data": {"message_id": msg_id, "full_content": text},
        })

    async def _send_error_message(
        self,
        db: AsyncSession,
        user_id: str,
        conversation_id: str,
        text: str,
    ):
        msg_id = make_id("msg_")
        msg = Message(
            id=msg_id,
            conversation_id=conversation_id,
            role="assistant",
            content=text,
            message_type="system",
        )
        db.add(msg)

        await self.ws.send_json(user_id, {
            "type": "stream_start",
            "data": {"message_id": msg_id, "conversation_id": conversation_id},
        })
        await self.ws.send_json(user_id, {
            "type": "stream_chunk",
            "data": {"message_id": msg_id, "content": text, "index": 0},
        })
        await self.ws.send_json(user_id, {
            "type": "stream_end",
            "data": {"message_id": msg_id, "full_content": text},
        })
