import json
import logging
from dataclasses import dataclass, field

from services.ai_service import AIService

logger = logging.getLogger(__name__)

CLASSIFIER_SYSTEM_PROMPT = """You are an intent classifier for a personal AI assistant called ClawChat.
Given a user message, you MUST call the classify_intent function to classify it.

Intents:
- general_chat: General conversation, questions, greetings, or anything that doesn't match other intents
- create_todo: User wants to create a task/todo (e.g., "remind me to buy groceries")
- query_todos: User wants to list or search tasks (e.g., "what are my tasks?")
- update_todo: User wants to modify a task (e.g., "change the priority of...")
- delete_todo: User wants to remove a task
- complete_todo: User wants to mark a task as done
- create_event: User wants to schedule a calendar event (e.g., "schedule a meeting tomorrow")
- query_events: User wants to check their calendar (e.g., "what's on my schedule?")
- update_event: User wants to modify an event
- delete_event: User wants to cancel an event
- create_memo: User wants to save a note (e.g., "note that the API key is...")
- query_memos: User wants to find notes (e.g., "what did I note about...")
- update_memo: User wants to edit a note
- delete_memo: User wants to remove a note
- search: User wants to search across all data (e.g., "find everything about VLA")
- delegate_task: User wants to assign a complex async task to the AI agent
- daily_briefing: User wants a summary of their day (e.g., "what's my day look like?")
- suggest_time: User wants scheduling suggestions (e.g., "when should I schedule a team meeting?")
- check_conflicts: User wants to check for scheduling conflicts (e.g., "do I have anything at 3pm?")
- analyze_schedule: User wants schedule analysis (e.g., "how busy am I this week?")

Extract relevant parameters from the message when applicable."""

INTENT_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "classify_intent",
            "description": "Classify the user's message intent and extract parameters",
            "parameters": {
                "type": "object",
                "properties": {
                    "intent": {
                        "type": "string",
                        "enum": [
                            "general_chat",
                            "create_todo",
                            "query_todos",
                            "update_todo",
                            "delete_todo",
                            "complete_todo",
                            "create_event",
                            "query_events",
                            "update_event",
                            "delete_event",
                            "create_memo",
                            "query_memos",
                            "update_memo",
                            "delete_memo",
                            "search",
                            "delegate_task",
                            "daily_briefing",
                            "suggest_time",
                            "check_conflicts",
                            "analyze_schedule",
                        ],
                        "description": "The classified intent of the user's message",
                    },
                    "title": {
                        "type": "string",
                        "description": "Title for todo/event/memo if applicable",
                    },
                    "description": {
                        "type": "string",
                        "description": "Description or body text if applicable",
                    },
                    "due_date": {
                        "type": "string",
                        "description": "Due date in ISO 8601 format if applicable",
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["low", "medium", "high", "urgent"],
                        "description": "Priority level if applicable",
                    },
                    "start_time": {
                        "type": "string",
                        "description": "Event start time in ISO 8601 format if applicable",
                    },
                    "end_time": {
                        "type": "string",
                        "description": "Event end time in ISO 8601 format if applicable",
                    },
                    "location": {
                        "type": "string",
                        "description": "Event location if applicable",
                    },
                    "query": {
                        "type": "string",
                        "description": "Search query if applicable",
                    },
                    "duration": {
                        "type": "integer",
                        "description": "Event duration in minutes for scheduling suggestions",
                    },
                    "preferred_date": {
                        "type": "string",
                        "description": "Preferred date in ISO 8601 format for scheduling",
                    },
                },
                "required": ["intent"],
            },
        },
    }
]


@dataclass
class IntentResult:
    intent: str = "general_chat"
    params: dict = field(default_factory=dict)


async def classify_intent(message: str, ai_service: AIService) -> IntentResult:
    try:
        response = await ai_service.function_call(
            system_prompt=CLASSIFIER_SYSTEM_PROMPT,
            user_message=message,
            tools=INTENT_TOOLS_SCHEMA,
            tool_choice={"type": "function", "function": {"name": "classify_intent"}},
        )

        choices = response.get("choices", [])
        if not choices:
            return IntentResult()

        msg = choices[0].get("message", {})
        tool_calls = msg.get("tool_calls", [])
        if not tool_calls:
            return IntentResult()

        args_str = tool_calls[0]["function"]["arguments"]
        args = json.loads(args_str)

        intent = args.pop("intent", "general_chat")
        # Remove None values from params
        params = {k: v for k, v in args.items() if v is not None}

        return IntentResult(intent=intent, params=params)

    except Exception:
        logger.exception("Intent classification failed, falling back to general_chat")
        return IntentResult()
