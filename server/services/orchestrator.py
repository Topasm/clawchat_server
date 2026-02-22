import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from constants import SYSTEM_PROMPT
from exceptions import AIUnavailableError
from models.agent_task import AgentTask
from models.conversation import Conversation
from models.message import Message
from services import (
    agent_task_service,
    briefing_service,
    calendar_service,
    memo_service,
    scheduling_service,
    search_service,
    todo_service,
)
from services.ai_service import AIService
from services.intent_classifier import classify_intent
from utils import make_id
from ws.manager import ConnectionManager

logger = logging.getLogger(__name__)

# Intents that map to module actions
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
    "suggest_time": "suggest a time for an event",
    "check_conflicts": "check for scheduling conflicts",
    "analyze_schedule": "analyze your schedule",
}


def _find_by_title(items, title: str):
    """Case-insensitive title substring match; prefers exact match."""
    title_lower = title.lower()
    matches = [x for x in items if title_lower in x.title.lower()]
    if len(matches) == 1:
        return matches[0]
    exact = [x for x in matches if x.title.lower() == title_lower]
    return exact[0] if exact else (matches[0] if matches else None)


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
                    await self._handle_module_action(
                        db, user_id, conversation_id, intent, params
                    )
                elif intent == "search":
                    await self._handle_search(
                        db, user_id, conversation_id, params, content
                    )
                elif intent == "delegate_task":
                    await self._handle_delegate_task(
                        db, user_id, conversation_id, message_id, params, content
                    )
                elif intent == "daily_briefing":
                    await self._handle_daily_briefing(
                        db, user_id, conversation_id
                    )
                else:
                    # Fallback to general chat
                    await self._handle_general_chat(
                        db, user_id, conversation_id, content
                    )

                # Auto-generate title for non-general-chat intents
                # (general_chat handles it internally)
                if intent != "general_chat":
                    conv = await db.get(Conversation, conversation_id)
                    if conv and not conv.title:
                        await self._generate_title(db, conv, content, user_id)

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

    async def _handle_delegate_task(
        self,
        db: AsyncSession,
        user_id: str,
        conversation_id: str,
        message_id: str,
        params: dict,
        content: str,
    ):
        instruction = params.get("instruction") or params.get("query") or content
        task_type = params.get("task_type", "research")

        # Detect complexity to determine agent type
        agent_type = agent_task_service.detect_agent_type(instruction)
        is_multi_agent = agent_type == "coordinator"

        task = await agent_task_service.create_task(
            db,
            task_type=task_type,
            instruction=instruction,
            conversation_id=conversation_id,
            message_id=message_id,
            agent_type=agent_type,
        )
        await db.flush()

        if is_multi_agent:
            msg = (
                f"Got it! This looks like a complex task, so I'm coordinating multiple agents "
                f"to work on it (ID: {task.id}). I'll keep you updated on progress."
            )
        else:
            msg = (
                f"Got it! I've queued that as a background task (ID: {task.id}). "
                "I'll notify you when it's done."
            )

        await self._send_assistant_message(
            db,
            user_id,
            conversation_id,
            "delegate_task",
            msg,
            metadata={
                "action_type": "task_delegated",
                "task_id": task.id,
                "agent_type": agent_type,
                "is_multi_agent": is_multi_agent,
            },
        )

        # Fire background execution with a fresh DB session
        async def _run_task():
            async with self.session_factory() as task_db:
                t = await task_db.get(AgentTask, task.id)
                if t:
                    await agent_task_service.execute_task(
                        task_db, t, self.ai, self.ws, user_id,
                        session_factory=self.session_factory,
                    )

        asyncio.create_task(_run_task())

    async def _handle_daily_briefing(
        self,
        db: AsyncSession,
        user_id: str,
        conversation_id: str,
    ):
        briefing = await briefing_service.generate_briefing(db, self.ai)
        await self._send_assistant_message(
            db, user_id, conversation_id, "daily_briefing", briefing
        )

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

        # Update conversation timestamp + auto-generate title
        conv = await db.get(Conversation, conversation_id)
        if conv:
            conv.updated_at = datetime.now(timezone.utc)
            if not conv.title:
                await self._generate_title(db, conv, content, user_id)

    async def _handle_search(
        self,
        db: AsyncSession,
        user_id: str,
        conversation_id: str,
        params: dict,
        content: str,
    ):
        query = params.get("query", content)
        try:
            hits, total = await search_service.search(db, query)
        except Exception:
            logger.exception("Search failed for query: %s", query)
            await self._send_assistant_message(
                db, user_id, conversation_id, "search",
                f"Sorry, I had trouble searching for '{query}'. Please try again.",
            )
            return

        if not hits:
            await self._send_assistant_message(
                db, user_id, conversation_id, "search",
                f"No results found for '{query}'.",
            )
            return

        lines = [f"Found {total} result(s) for '{query}':"]
        for h in hits[:10]:
            label = h.title or h.type
            preview = h.preview[:80] + "..." if len(h.preview) > 80 else h.preview
            lines.append(f"- **[{h.type}]** {label}: {preview}")
        if total > 10:
            lines.append(f"...and {total - 10} more.")
        await self._send_assistant_message(
            db, user_id, conversation_id, "search", "\n".join(lines),
        )

    async def _handle_module_action(
        self,
        db: AsyncSession,
        user_id: str,
        conversation_id: str,
        intent: str,
        params: dict,
    ):
        response_text, action_metadata = await self._execute_module_intent(db, intent, params)
        await self._send_assistant_message(
            db, user_id, conversation_id, intent, response_text, metadata=action_metadata
        )

        # Notify frontend to refresh module data
        if action_metadata:
            await self.ws.send_json(user_id, {
                "type": "module_data_changed",
                "data": {"module": action_metadata.get("module")},
            })

    async def _execute_module_intent(
        self, db: AsyncSession, intent: str, params: dict
    ) -> tuple[str, dict | None]:
        try:
            if intent == "create_todo":
                todo = await todo_service.create_todo(
                    db,
                    title=params.get("title", "Untitled task"),
                    description=params.get("description"),
                    priority=params.get("priority", "medium"),
                )
                return (
                    f"Created task: '{todo.title}' with {todo.priority} priority.",
                    {"action_type": "todo_created", "module": "todos", "todo_id": todo.id, "todo_title": todo.title},
                )

            elif intent == "query_todos":
                todos, total = await todo_service.get_todos(db)
                if not todos:
                    return "You don't have any tasks yet.", None
                lines = [f"You have {total} task(s):"]
                for t in todos[:5]:
                    lines.append(f"- [{t.status}] {t.title}")
                if total > 5:
                    lines.append(f"...and {total - 5} more.")
                return "\n".join(lines), None

            elif intent == "complete_todo":
                title = params.get("title", "")
                if not title:
                    return "Which task would you like to complete? Please mention the task name.", None
                todos, _ = await todo_service.get_todos(db, limit=100)
                todo = _find_by_title(todos, title)
                if not todo:
                    return f"I couldn't find a task matching '{title}'. Try listing your tasks first.", None
                todo = await todo_service.update_todo(db, todo.id, status="completed")
                return (
                    f"Marked '{todo.title}' as complete.",
                    {"action_type": "todo_completed", "module": "todos", "todo_id": todo.id, "todo_title": todo.title},
                )

            elif intent == "create_event":
                title = params.get("title", "Untitled event")
                start_time = params.get("start_time")
                if not start_time:
                    return (
                        f"I'd create event '{title}', but I need a start time. "
                        "When should it be?",
                        None,
                    )
                event = await calendar_service.create_event(
                    db,
                    title=title,
                    description=params.get("description"),
                    start_time=datetime.fromisoformat(start_time),
                    end_time=(
                        datetime.fromisoformat(params["end_time"])
                        if params.get("end_time")
                        else None
                    ),
                    location=params.get("location"),
                )
                return (
                    f"Created event: '{event.title}' starting at {event.start_time}.",
                    {"action_type": "event_created", "module": "events", "event_id": event.id, "event_title": event.title, "event_start_time": event.start_time.isoformat()},
                )

            elif intent == "query_events":
                events, total = await calendar_service.get_events(db)
                if not events:
                    return "You don't have any upcoming events.", None
                lines = [f"You have {total} event(s):"]
                for e in events[:5]:
                    st = e["start_time"] if isinstance(e, dict) else e.start_time
                    t = e["title"] if isinstance(e, dict) else e.title
                    lines.append(f"- {t} at {st}")
                if total > 5:
                    lines.append(f"...and {total - 5} more.")
                return "\n".join(lines), None

            elif intent == "create_memo":
                memo = await memo_service.create_memo(
                    db,
                    title=params.get("title", "Quick Note"),
                    content=params.get("description", params.get("title", "")),
                )
                return (
                    f"Saved memo: '{memo.title}'.",
                    {"action_type": "memo_created", "module": "memos", "memo_id": memo.id, "memo_title": memo.title},
                )

            elif intent == "query_memos":
                memos, total = await memo_service.get_memos(db)
                if not memos:
                    return "You don't have any memos yet.", None
                lines = [f"You have {total} memo(s):"]
                for m in memos[:5]:
                    preview = (
                        m.content[:60] + "..." if len(m.content) > 60 else m.content
                    )
                    lines.append(f"- {m.title}: {preview}")
                if total > 5:
                    lines.append(f"...and {total - 5} more.")
                return "\n".join(lines), None

            elif intent == "update_todo":
                title = params.get("title", "")
                if not title:
                    return "Which task would you like to update? Please mention the task name.", None
                todos, _ = await todo_service.get_todos(db, limit=100)
                todo = _find_by_title(todos, title)
                if not todo:
                    return f"I couldn't find a task matching '{title}'. Try listing your tasks first.", None
                updates = {}
                if params.get("description"):
                    updates["description"] = params["description"]
                if params.get("priority"):
                    updates["priority"] = params["priority"]
                if params.get("due_date"):
                    updates["due_date"] = datetime.fromisoformat(params["due_date"])
                if params.get("status"):
                    updates["status"] = params["status"]
                if not updates:
                    return f"I found '{todo.title}', but I'm not sure what to change. What would you like to update?", None
                todo = await todo_service.update_todo(db, todo.id, **updates)
                return (
                    f"Updated task '{todo.title}'.",
                    {"action_type": "todo_updated", "module": "todos", "todo_id": todo.id, "todo_title": todo.title},
                )

            elif intent == "delete_todo":
                title = params.get("title", "")
                if not title:
                    return "Which task would you like to delete? Please mention the task name.", None
                todos, _ = await todo_service.get_todos(db, limit=100)
                todo = _find_by_title(todos, title)
                if not todo:
                    return f"I couldn't find a task matching '{title}'. Try listing your tasks first.", None
                deleted_title = todo.title
                deleted_id = todo.id
                await todo_service.delete_todo(db, todo.id)
                return (
                    f"Deleted task '{deleted_title}'.",
                    {"action_type": "todo_deleted", "module": "todos", "todo_id": deleted_id, "todo_title": deleted_title},
                )

            elif intent == "update_event":
                title = params.get("title", "")
                if not title:
                    return "Which event would you like to update? Please mention the event name.", None
                events, _ = await calendar_service.get_events(db, limit=100)
                event = _find_by_title(events, title)
                if not event:
                    return f"I couldn't find an event matching '{title}'. Try checking your calendar first.", None
                updates = {}
                if params.get("description"):
                    updates["description"] = params["description"]
                if params.get("start_time"):
                    updates["start_time"] = datetime.fromisoformat(params["start_time"])
                if params.get("end_time"):
                    updates["end_time"] = datetime.fromisoformat(params["end_time"])
                if params.get("location"):
                    updates["location"] = params["location"]
                if not updates:
                    return f"I found '{event.title}', but I'm not sure what to change. What would you like to update?", None
                event = await calendar_service.update_event(db, event.id, **updates)
                return (
                    f"Updated event '{event.title}'.",
                    {"action_type": "event_updated", "module": "events", "event_id": event.id, "event_title": event.title},
                )

            elif intent == "delete_event":
                title = params.get("title", "")
                if not title:
                    return "Which event would you like to delete? Please mention the event name.", None
                events, _ = await calendar_service.get_events(db, limit=100)
                event = _find_by_title(events, title)
                if not event:
                    return f"I couldn't find an event matching '{title}'. Try checking your calendar first.", None
                deleted_title = event.title
                deleted_id = event.id
                await calendar_service.delete_event(db, event.id)
                return (
                    f"Deleted event '{deleted_title}'.",
                    {"action_type": "event_deleted", "module": "events", "event_id": deleted_id, "event_title": deleted_title},
                )

            elif intent == "update_memo":
                title = params.get("title", "")
                if not title:
                    return "Which memo would you like to update? Please mention the memo name.", None
                memos, _ = await memo_service.get_memos(db, limit=100)
                memo = _find_by_title(memos, title)
                if not memo:
                    return f"I couldn't find a memo matching '{title}'. Try listing your memos first.", None
                updates = {}
                if params.get("description"):
                    updates["content"] = params["description"]
                if params.get("new_title"):
                    updates["title"] = params["new_title"]
                if not updates:
                    return f"I found '{memo.title}', but I'm not sure what to change. What would you like to update?", None
                memo = await memo_service.update_memo(db, memo.id, **updates)
                return (
                    f"Updated memo '{memo.title}'.",
                    {"action_type": "memo_updated", "module": "memos", "memo_id": memo.id, "memo_title": memo.title},
                )

            elif intent == "delete_memo":
                title = params.get("title", "")
                if not title:
                    return "Which memo would you like to delete? Please mention the memo name.", None
                memos, _ = await memo_service.get_memos(db, limit=100)
                memo = _find_by_title(memos, title)
                if not memo:
                    return f"I couldn't find a memo matching '{title}'. Try listing your memos first.", None
                deleted_title = memo.title
                deleted_id = memo.id
                await memo_service.delete_memo(db, memo.id)
                return (
                    f"Deleted memo '{deleted_title}'.",
                    {"action_type": "memo_deleted", "module": "memos", "memo_id": deleted_id, "memo_title": deleted_title},
                )

            elif intent == "suggest_time":
                title = params.get("title", "Meeting")
                duration = params.get("duration", 60)
                preferred = None
                if params.get("preferred_date"):
                    preferred = datetime.fromisoformat(params["preferred_date"])
                suggestions = await scheduling_service.suggest_best_time(
                    db, self.ai, title, int(duration), preferred,
                )
                if not suggestions:
                    return "I couldn't find any available time slots in the next week. Your schedule looks quite full!", None
                lines = [f"Here are my top suggestions for '{title}':"]
                for i, s in enumerate(suggestions, 1):
                    start_dt = datetime.fromisoformat(s["start"])
                    lines.append(f"{i}. {start_dt.strftime('%A, %b %d at %I:%M %p')} — {s.get('reason', '')}")
                lines.append("\nJust say 'schedule it at [time]' to create the event.")
                return (
                    "\n".join(lines),
                    {"action_type": "scheduling_suggestions", "suggestions": suggestions, "title": title},
                )

            elif intent == "check_conflicts":
                start_time = params.get("start_time")
                if not start_time:
                    now = datetime.now(timezone.utc)
                    start_time = now.isoformat()
                st = datetime.fromisoformat(start_time)
                end_time = params.get("end_time")
                et = datetime.fromisoformat(end_time) if end_time else st + timedelta(hours=1)
                conflicts = await scheduling_service.find_conflicts(db, st, et)
                if not conflicts:
                    return (
                        "You're free during that time! No scheduling conflicts found.",
                        {"action_type": "no_conflicts"},
                    )
                lines = [f"You have {len(conflicts)} conflict(s):"]
                for c in conflicts:
                    lines.append(f"- {c['title']} ({c['start_time']})")
                return (
                    "\n".join(lines),
                    {"action_type": "conflicts_found", "conflicts": conflicts},
                )

            elif intent == "analyze_schedule":
                now = datetime.now(timezone.utc)
                range_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                range_end = range_start + timedelta(days=7)
                events, total = await calendar_service.get_events(db, start_after=range_start, start_before=range_end, limit=100)
                if not events:
                    return "Your schedule for the next 7 days is completely clear!", None
                # Build summary for AI
                event_lines = []
                for e in events:
                    t = e["title"] if isinstance(e, dict) else e.title
                    st = e["start_time"] if isinstance(e, dict) else e.start_time
                    event_lines.append(f"- {t} at {st}")
                event_summary = "\n".join(event_lines)
                analysis = await self.ai.generate_completion(
                    system_prompt="You are a scheduling analyst. Summarize the user's week concisely — highlight busy days, free days, and any potential issues like back-to-back meetings.",
                    user_message=f"Here are my events for the next 7 days:\n{event_summary}",
                )
                return analysis, None

            else:
                action = MODULE_INTENTS.get(intent, intent)
                title = params.get("title", "")
                detail = f": '{title}'" if title else ""
                return f"I understood you want to {action}{detail}. This action is coming soon!", None

        except Exception:
            logger.exception("Module action failed for intent %s", intent)
            action = MODULE_INTENTS.get(intent, intent)
            return f"I tried to {action} but something went wrong. Please try again.", None

    async def _generate_title(
        self,
        db: AsyncSession,
        conv: Conversation,
        user_message: str,
        user_id: str,
    ):
        """Auto-generate a conversation title from the first user message."""
        try:
            title = await self.ai.generate_title(user_message)
            conv.title = title
            # Notify client of title update via WS
            await self.ws.send_json(user_id, {
                "type": "conversation_updated",
                "data": {"conversation_id": conv.id, "title": title},
            })
        except Exception:
            logger.warning("Failed to generate title for conversation %s", conv.id)

    async def _send_assistant_message(
        self,
        db: AsyncSession,
        user_id: str,
        conversation_id: str,
        intent: str,
        text: str,
        metadata: dict | None = None,
    ):
        msg_id = make_id("msg_")
        msg = Message(
            id=msg_id,
            conversation_id=conversation_id,
            role="assistant",
            content=text,
            intent=intent,
            metadata_json=json.dumps(metadata) if metadata else None,
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
        stream_end_data: dict = {"message_id": msg_id, "full_content": text}
        if metadata:
            stream_end_data["metadata"] = metadata
        await self.ws.send_json(user_id, {
            "type": "stream_end",
            "data": stream_end_data,
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
