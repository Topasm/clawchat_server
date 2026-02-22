import json
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from auth.dependencies import get_current_user
from constants import SYSTEM_PROMPT
from database import get_db
from exceptions import NotFoundError
from models.conversation import Conversation
from models.message import Message
from schemas.chat import (
    ConversationDetailResponse,
    ConversationResponse,
    CreateConversationRequest,
    MessageEditRequest,
    MessageResponse,
    SendMessageRequest,
    SendMessageResponse,
)
from schemas.common import PaginatedResponse
from utils import make_id

router = APIRouter()


@router.get("/conversations", response_model=PaginatedResponse[ConversationResponse])
async def list_conversations(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    archived: bool = False,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    offset = (page - 1) * limit

    count_q = select(func.count(Conversation.id)).where(
        Conversation.is_archived == archived
    )
    total = (await db.execute(count_q)).scalar() or 0

    q = (
        select(Conversation)
        .where(Conversation.is_archived == archived)
        .order_by(Conversation.updated_at.desc())
        .offset(offset)
        .limit(limit)
    )
    rows = (await db.execute(q)).scalars().all()

    items = []
    for conv in rows:
        # Get last message preview
        last_msg_q = (
            select(Message.content)
            .where(Message.conversation_id == conv.id)
            .order_by(Message.created_at.desc())
            .limit(1)
        )
        last_msg = (await db.execute(last_msg_q)).scalar()
        preview = last_msg[:100] if last_msg else None

        items.append(
            ConversationResponse(
                id=conv.id,
                title=conv.title,
                created_at=conv.created_at,
                updated_at=conv.updated_at,
                is_archived=conv.is_archived,
                last_message=preview,
            )
        )

    return PaginatedResponse(items=items, total=total, page=page, limit=limit)


@router.post("/conversations", response_model=ConversationResponse, status_code=201)
async def create_conversation(
    body: CreateConversationRequest,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    conv = Conversation(title=body.title)
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    return ConversationResponse(
        id=conv.id,
        title=conv.title,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        is_archived=conv.is_archived,
    )


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    conv = await db.get(Conversation, conversation_id)
    if not conv:
        raise NotFoundError("Conversation not found")

    msg_q = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
    )
    messages = (await db.execute(msg_q)).scalars().all()

    return ConversationDetailResponse(
        id=conv.id,
        title=conv.title,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        is_archived=conv.is_archived,
        messages=[MessageResponse.model_validate(m) for m in messages],
    )


@router.delete("/conversations/{conversation_id}")
async def archive_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    conv = await db.get(Conversation, conversation_id)
    if not conv:
        raise NotFoundError("Conversation not found")
    conv.is_archived = True
    conv.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"message": "Conversation archived"}


@router.post("/stream")
async def stream_chat(
    body: SendMessageRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    conv = await db.get(Conversation, body.conversation_id)
    if not conv:
        raise NotFoundError("Conversation not found")

    # Save user message
    user_msg = Message(
        id=make_id("msg_"),
        conversation_id=body.conversation_id,
        role="user",
        content=body.content,
    )
    db.add(user_msg)
    conv.updated_at = datetime.now(timezone.utc)
    await db.commit()

    # Build message history (last 20)
    q = (
        select(Message)
        .where(Message.conversation_id == body.conversation_id)
        .order_by(Message.created_at.desc())
        .limit(20)
    )
    rows = (await db.execute(q)).scalars().all()
    history = list(reversed(rows))

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in history:
        messages.append({"role": msg.role, "content": msg.content})

    assistant_msg_id = make_id("msg_")
    ai_service = request.app.state.ai_service
    session_factory = request.app.state.session_factory

    async def event_generator():
        meta = json.dumps(
            {"conversation_id": body.conversation_id, "message_id": assistant_msg_id}
        )
        yield f"data: {meta}\n\n"

        accumulated = ""
        try:
            async for token in ai_service.stream_completion(messages):
                accumulated += token
                yield f"data: {json.dumps({'token': token})}\n\n"
        except Exception:
            if not accumulated:
                error_text = "Sorry, an error occurred while generating a response."
                accumulated = error_text
                yield f"data: {json.dumps({'token': error_text})}\n\n"

        yield "data: [DONE]\n\n"

        # Save assistant message with a fresh session
        async with session_factory() as save_db:
            assistant_msg = Message(
                id=assistant_msg_id,
                conversation_id=body.conversation_id,
                role="assistant",
                content=accumulated,
            )
            save_db.add(assistant_msg)
            save_conv = await save_db.get(Conversation, body.conversation_id)
            if save_conv:
                save_conv.updated_at = datetime.now(timezone.utc)
                # Auto-generate title on first message
                if not save_conv.title:
                    try:
                        title = await ai_service.generate_title(body.content)
                        save_conv.title = title
                        yield f"data: {json.dumps({'title_generated': title})}\n\n"
                    except Exception:
                        pass
            await save_db.commit()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/send", response_model=SendMessageResponse, status_code=202)
async def send_message(
    body: SendMessageRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    conv = await db.get(Conversation, body.conversation_id)
    if not conv:
        raise NotFoundError("Conversation not found")

    msg = Message(
        id=make_id("msg_"),
        conversation_id=body.conversation_id,
        role="user",
        content=body.content,
    )
    db.add(msg)
    conv.updated_at = datetime.now(timezone.utc)
    await db.commit()

    # Dispatch AI processing in background
    orchestrator = request.app.state.orchestrator
    background_tasks.add_task(
        orchestrator.handle_message,
        user_id=_user,
        conversation_id=body.conversation_id,
        message_id=msg.id,
        content=body.content,
    )

    return SendMessageResponse(
        message_id=msg.id,
        conversation_id=body.conversation_id,
    )


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=PaginatedResponse[MessageResponse],
)
async def list_messages(
    conversation_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    conv = await db.get(Conversation, conversation_id)
    if not conv:
        raise NotFoundError("Conversation not found")

    offset = (page - 1) * limit
    count_q = select(func.count(Message.id)).where(
        Message.conversation_id == conversation_id
    )
    total = (await db.execute(count_q)).scalar() or 0

    q = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
        .offset(offset)
        .limit(limit)
    )
    rows = (await db.execute(q)).scalars().all()

    return PaginatedResponse(
        items=[MessageResponse.model_validate(m) for m in rows],
        total=total,
        page=page,
        limit=limit,
    )


@router.delete("/conversations/{conversation_id}/messages/{message_id}")
async def delete_message(
    conversation_id: str,
    message_id: str,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    conv = await db.get(Conversation, conversation_id)
    if not conv:
        raise NotFoundError("Conversation not found")

    msg = await db.get(Message, message_id)
    if not msg or msg.conversation_id != conversation_id:
        raise NotFoundError("Message not found")

    await db.delete(msg)
    await db.commit()
    return {"message": "Message deleted"}


@router.put(
    "/conversations/{conversation_id}/messages/{message_id}",
    response_model=MessageResponse,
)
async def edit_message(
    conversation_id: str,
    message_id: str,
    body: MessageEditRequest,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    conv = await db.get(Conversation, conversation_id)
    if not conv:
        raise NotFoundError("Conversation not found")

    msg = await db.get(Message, message_id)
    if not msg or msg.conversation_id != conversation_id:
        raise NotFoundError("Message not found")

    msg.content = body.content
    conv.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(msg)
    return MessageResponse.model_validate(msg)
