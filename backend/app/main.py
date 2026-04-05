"""Knowledge OS Backend - FastAPI Application"""
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.vendor.slowapi_compat import (
    RateLimitExceeded,
    SlowAPIMiddleware,
    _rate_limit_exceeded_handler,
)

from app.config import settings
from app.database.qdrant_client import qdrant_manager
from app.database.sqlite import sqlite_manager
from app.logging_config import AppMetrics, bind_request_context, clear_request_context, configure_logging
from app.middleware.rate_limit import limiter, read_rate_limit
from app.services.embedding import embedding_service
from app.services.backup import backup_service
from app.services.auth import auth_service
from app.services.file_watcher import file_watcher_service
from app.services.websocket_manager import websocket_manager
from app.services.collaboration import collaboration_manager

# Import routers
from app.routers import objects, blocks, tasks, search, agents, files, relations, settings as settings_router, auth as auth_router, collaboration, system

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    # Startup
    logger.info("🚀 Starting Knowledge OS Backend...")
    auth_service.log_secret_configuration_warning()
    
    # Initialize databases first
    logger.info("📦 Initializing Qdrant...")
    await qdrant_manager.initialize()
    
    logger.info("📦 Initializing SQLite...")
    await sqlite_manager.initialize()
    
    # Initialize embedding service (needed by other services)
    logger.info("📦 Initializing embedding service...")
    await embedding_service.initialize()
    
    # Initialize other services
    logger.info("📦 Initializing backup service...")
    await backup_service.start()
    
    logger.info("📦 Initializing file watcher service...")
    await file_watcher_service.start()

    logger.info("📦 Initializing collaboration service...")
    await collaboration_manager.start()

    logger.info("✅ Knowledge OS Backend started successfully!")
    
    yield
    
    # Shutdown
    logger.info("🛑 Shutting down Knowledge OS Backend...")
    
    await file_watcher_service.stop()
    await backup_service.stop()
    await collaboration_manager.stop()
    await embedding_service.close()
    await sqlite_manager.close()
    await qdrant_manager.close()
    
    logger.info("✅ Knowledge OS Backend stopped")


# Create FastAPI app
app = FastAPI(
    title="Knowledge OS API",
    description="API for Knowledge OS - A knowledge management system with AI agent integration",
    version="0.1.0",
    lifespan=lifespan
)
app.state.limiter = limiter
app.state.metrics = AppMetrics.create()
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Configure CORS with configurable origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SlowAPIMiddleware)


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    """Attach request id, timing, and error metrics to every HTTP request."""
    request_id = str(uuid.uuid4())
    bind_request_context(request_id)
    request.state.request_id = request_id

    start = time.perf_counter()
    response = None
    app.state.metrics.request_count += 1

    try:
        response = await call_next(request)
        if response.status_code >= 500:
            app.state.metrics.error_count += 1
        return response
    except Exception:
        app.state.metrics.error_count += 1
        logger.error(
            "Unhandled request error",
            exc_info=True,
            extra={
                "method": request.method,
                "path": request.url.path,
                "query": str(request.url.query),
            },
        )
        raise
    finally:
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        if response is not None:
            response.headers["X-Request-ID"] = request_id

        logger.info(
            "Request completed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": getattr(response, "status_code", 500),
                "duration_ms": duration_ms,
            },
        )
        if duration_ms > 5000:
            logger.warning(
                "Slow request detected",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": getattr(response, "status_code", 500),
                    "duration_ms": duration_ms,
                },
            )
        clear_request_context()

# Include routers
app.include_router(auth_router.router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(objects.router, prefix="/api/v1/objects", tags=["Objects"])
app.include_router(blocks.router, prefix="/api/v1/blocks", tags=["Blocks"])
app.include_router(tasks.router, prefix="/api/v1/tasks", tags=["Tasks"])
app.include_router(search.router, prefix="/api/v1/search", tags=["Search"])
app.include_router(agents.router, prefix="/api/v1/agents", tags=["Agents"])
app.include_router(files.router, prefix="/api/v1/files", tags=["Files"])
app.include_router(relations.router, prefix="/api/v1/relations", tags=["Relations"])
app.include_router(settings_router.router, prefix="/api/v1/settings", tags=["Settings"])
app.include_router(collaboration.router, prefix="/api/v1/collaboration", tags=["Collaboration"])
app.include_router(system.router, prefix="/api/v1/system", tags=["System"])


@app.get("/health")
@read_rate_limit
async def health_check(request: Request):
    """Health check endpoint"""
    return {
        "status": "healthy",
        "version": "0.1.0"
    }


@app.get("/")
@read_rate_limit
async def root(request: Request):
    """Root endpoint"""
    return {
        "message": "Knowledge OS API",
        "version": "0.1.0",
        "docs": "/docs"
    }


@app.websocket("/ws")
@app.websocket("/ws/system")
@app.websocket("/ws/agents/{agent_name}")
async def websocket_endpoint(websocket: WebSocket, agent_name: str = "system"):
    """Shared WebSocket endpoint for live updates."""
    await websocket_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            await websocket_manager.handle_message(websocket, data)
    except WebSocketDisconnect:
        logger.debug("WebSocket disconnected for agent '%s'", agent_name)
        websocket_manager.disconnect(websocket)
    except Exception:
        logger.exception("Unhandled WebSocket error for agent '%s'", agent_name)
        websocket_manager.disconnect(websocket)
        raise


# Note: Collaboration WebSocket is handled by the collaboration router at /api/collaboration/ws/{object_id}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=getattr(settings, "host", "0.0.0.0"),
        port=int(getattr(settings, "port", 8000)),
    )
