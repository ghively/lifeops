"""Task Models"""

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class TaskStatus(str, Enum):
    """Task status enum"""

    TODO = "todo"
    IN_PROGRESS = "in-progress"
    BLOCKED = "blocked"
    REVIEW = "review"
    DONE = "done"


class Priority(str, Enum):
    """Task priority enum"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class Task(BaseModel):
    """Task model"""

    id: str
    type: str = "task"
    title: str
    content: Optional[str] = None
    properties: Dict[str, Any] = {}


class TaskCreate(BaseModel):
    """Task creation model"""

    title: str
    content: Optional[str] = None
    priority: Priority = Priority.MEDIUM
    assigned_to: Optional[str] = None
    due_date: Optional[str] = None


class TaskUpdate(BaseModel):
    """Task update model"""

    title: Optional[str] = None
    content: Optional[str] = None
    priority: Optional[Priority] = None
    status: Optional[TaskStatus] = None
    assigned_to: Optional[str] = None
    due_date: Optional[str] = None


class TaskListResponse(BaseModel):
    """Task list response"""

    tasks: List[Dict[str, Any]]
