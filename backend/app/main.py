"""Knowledge OS Backend - FastAPI Application"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

try:
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from slowapi.middleware import SlowAPIMiddleware
except ImportError:  # pragma: no cover - used in offline CI/dev environments
    from app.vendor.slowapi_compat import (
        RateLimitExceeded,
        SlowAPIMiddleware,
        _rate_limit_exceeded_handler,
    )

from app.config import settings
from app.database.qdrant_client import qdrant_manager
from app.database.sqlite import sqlite_manager
from app.middleware.rate_limit import limiter, read_rate_limit
from app.services.embedding import embedding_service
from app.services.backup import backup_service
from app.services.auth import auth_service
from app.services.file_watcher import file_watcher_service
from app.services.websocket_manager import websocket_manager
from app.services.collaboration import collaboration_manager

# Import routers
from app.routers import objects, blocks, tasks, search, agents, files, relations, settings as settings_router, auth as auth_router, collaboration

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
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

# Include routers
app.include_router(auth_router.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(objects.router, prefix="/api/objects", tags=["Objects"])
app.include_router(blocks.router, prefix="/api/blocks", tags=["Blocks"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["Tasks"])
app.include_router(search.router, prefix="/api/search", tags=["Search"])
app.include_router(agents.router, prefix="/api/agents", tags=["Agents"])
app.include_router(files.router, prefix="/api/files", tags=["Files"])
app.include_router(relations.router, prefix="/api/relations", tags=["Relations"])
app.include_router(settings_router.router, prefix="/api/settings", tags=["Settings"])
app.include_router(collaboration.router, prefix="/api/collaboration", tags=["Collaboration"])


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
        websocket_manager.disconnect(websocket)
    except Exception:
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
