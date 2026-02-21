import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import async_session_factory, init_db
from exceptions import AppError, app_error_handler
from routers import auth as auth_router
from routers import calendar as calendar_router
from routers import chat as chat_router
from routers import memo as memo_router
from routers import notifications as notifications_router
from routers import search as search_router
from routers import today as today_router
from routers import todo as todo_router
from services.ai_service import AIService
from services.orchestrator import Orchestrator
from services.scheduler import Scheduler
from ws.handler import websocket_endpoint
from ws.manager import ws_manager

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    # Create AI service
    ai_service = AIService(
        base_url=settings.ai_base_url,
        api_key=settings.ai_api_key,
        model=settings.ai_model,
        provider=settings.ai_provider,
    )
    app.state.ai_service = ai_service

    # Create orchestrator
    app.state.orchestrator = Orchestrator(
        ai_service=ai_service,
        ws_manager=ws_manager,
        session_factory=async_session_factory,
    )

    app.state.session_factory = async_session_factory

    # Check AI connectivity
    app.state.ai_connected = await ai_service.health_check()

    # Start background scheduler if enabled
    if settings.enable_scheduler:
        scheduler = Scheduler(
            session_factory=async_session_factory,
            ai_service=ai_service,
            ws_manager=ws_manager,
        )
        scheduler.start()
        app.state.scheduler = scheduler
        logger.info("Background scheduler started")
    else:
        app.state.scheduler = None

    yield

    # Stop scheduler before closing AI service
    if app.state.scheduler:
        await app.state.scheduler.stop()

    await ai_service.close()


app = FastAPI(title="ClawChat Server", version="0.1.0", lifespan=lifespan)

app.add_exception_handler(AppError, app_error_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth_router.router, prefix="/api/auth", tags=["auth"])
app.include_router(chat_router.router, prefix="/api/chat", tags=["chat"])
app.include_router(todo_router.router, prefix="/api/todos", tags=["todos"])
app.include_router(calendar_router.router, prefix="/api/events", tags=["calendar"])
app.include_router(memo_router.router, prefix="/api/memos", tags=["memos"])
app.include_router(search_router.router, prefix="/api/search", tags=["search"])
app.include_router(today_router.router, prefix="/api/today", tags=["today"])
app.include_router(notifications_router.router, prefix="/api/notifications", tags=["notifications"])

app.websocket("/ws")(websocket_endpoint)


@app.get("/api/health")
async def health():
    ai_connected = getattr(app.state, "ai_connected", False)
    return {
        "status": "ok" if ai_connected else "degraded",
        "version": "0.1.0",
        "ai_provider": settings.ai_provider,
        "ai_model": settings.ai_model,
        "ai_connected": ai_connected,
    }
