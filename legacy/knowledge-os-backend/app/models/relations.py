"""Relation models."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class RelationCreate(BaseModel):
    """Relation creation model."""

    source_id: str
    source_type: str = "object"
    target_id: str
    target_type: str = "object"
    relation_type: str
    context: str = ""


class RelationUpdate(BaseModel):
    """Relation update model."""

    relation_type: Optional[str] = None
    context: Optional[str] = None


class RelationListResponse(BaseModel):
    """Relation list response."""

    relations: List[Dict[str, Any]] = Field(default_factory=list)
