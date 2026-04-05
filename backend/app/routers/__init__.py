"""Routers package"""
from .objects import router as objects_router
from .blocks import router as blocks_router
from .tasks import router as tasks_router
from .search import router as search_router
from .agents import router as agents_router
from .files import router as files_router
from .settings import router as settings_router
from .relations import router as relations_router
from .system import router as system_router
from .agent_chat import router as agent_chat_router
from . import auth as auth_router

__all__ = [
    'objects_router',
    'blocks_router',
    'tasks_router',
    'search_router',
    'agents_router',
    'files_router',
    'settings_router',
    'relations_router',
    'system_router',
    'agent_chat_router',
    'auth_router',
]
