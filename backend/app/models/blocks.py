"""Block Models"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class BlockProperties(BaseModel):
    """Block properties"""

    checked: Optional[bool] = None
    language: Optional[str] = None
    url: Optional[str] = None
    collapsed: Optional[bool] = None
    assigned_to: Optional[str] = None
    due_date: Optional[str] = None
    priority: Optional[str] = None


class Block(BaseModel):
    """Block model"""

    id: str
    object_id: str
    type: str
    content: str
    level: int = 0
    order: int = 0
    properties: BlockProperties = Field(default_factory=BlockProperties)
    parent_id: Optional[str] = None
    references: List[str] = Field(default_factory=list)
    referenced_by: List[str] = Field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class BlockCreate(BaseModel):
    """Block creation model"""

    id: Optional[str] = None
    object_id: str
    type: str = "paragraph"
    content: str = ""
    level: int = 0
    properties: Optional[BlockProperties] = None
    parent_id: Optional[str] = None
    order: Optional[int] = None


class BlockUpdate(BaseModel):
    """Block update model"""

    content: Optional[str] = None
    type: Optional[str] = None
    level: Optional[int] = None
    properties: Optional[BlockProperties] = None
    order: Optional[int] = None
    parent_id: Optional[str] = None


class BlockListResponse(BaseModel):
    """Block list response"""

    blocks: List[Dict[str, Any]]


class BatchBlockUpdateItem(BaseModel):
    """Single block update in a batch request."""

    id: str
    order: Optional[int] = None
    parent_id: Optional[str] = None
    level: Optional[int] = None


class BatchBlockUpdateRequest(BaseModel):
    """Batch update block order and nesting."""

    blocks: List[BatchBlockUpdateItem] = Field(default_factory=list)


class SyncBlockItem(BaseModel):
    """A single block in a sync request."""

    id: Optional[str] = None
    type: str = "paragraph"
    content: str = ""
    level: int = 0
    properties: Optional[Dict[str, Any]] = None
    parent_id: Optional[str] = None


class SyncBlocksRequest(BaseModel):
    """Replace an object's block set in a single request."""

    blocks: List[SyncBlockItem] = Field(default_factory=list)
