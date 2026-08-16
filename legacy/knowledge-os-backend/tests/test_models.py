"""
Tests for Pydantic model validation.
"""

import pytest
from pydantic import ValidationError

from app.models.blocks import Block, BlockCreate, BlockListResponse, BlockProperties, BlockUpdate
from app.models.objects import Object, ObjectCreate, ObjectListResponse, ObjectProperties, ObjectUpdate
from app.models.relations import RelationCreate, RelationListResponse, RelationUpdate
from app.models.tasks import Priority, Task, TaskCreate, TaskListResponse, TaskStatus, TaskUpdate


@pytest.mark.asyncio
class TestObjectModels:
    """Test cases for object Pydantic models."""

    def test_object_properties_valid(self):
        """Test creating valid object properties."""
        data = {
            "tags": ["test", "sample"],
            "status": "active",
            "priority": "high",
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
        }

        props = ObjectProperties(**data)

        assert props.tags == ["test", "sample"]
        assert props.status == "active"
        assert props.priority == "high"

    def test_object_properties_minimal(self):
        """Test creating object properties with minimal fields."""
        props = ObjectProperties()

        # Should create with defaults
        assert props.tags == []
        assert props.status is None

    def test_object_create_valid(self):
        """Test creating object with ObjectCreate model."""
        data = {
            "title": "New Object",
            "content": "Content",
            "type": "note",
        }

        obj = ObjectCreate(**data)

        assert obj.title == "New Object"
        assert obj.type == "note"

    def test_object_create_with_all_fields(self):
        """Test creating object with all optional fields."""
        data = {
            "title": "Complete Object",
            "content": "Content",
            "type": "note",
            "properties": {
                "tags": ["test"],
                "status": "active",
                "priority": "high",
            },
            "icon": "📝",
            "layout": "default",
        }

        obj = ObjectCreate(**data)

        assert obj.title == "Complete Object"
        assert obj.icon == "📝"
        assert obj.layout == "default"
        assert obj.properties.tags == ["test"]
        assert obj.properties.status == "active"
        assert obj.properties.priority == "high"

    def test_object_update_partial(self):
        """Test updating object with partial data."""
        data = {
            "title": "Updated Title",
        }

        obj = ObjectUpdate(**data)

        assert obj.title == "Updated Title"

    def test_object_update_empty(self):
        """Test updating object with no fields."""
        obj = ObjectUpdate()

        # Should allow empty update
        assert obj is not None

    def test_object_model_invalid_type(self):
        """Test object with invalid type."""
        data = {
            "title": "Test",
            "type": "invalid_type",
        }

        # Type is just a string, no validation
        obj = ObjectCreate(**data)
        assert obj.type == "invalid_type"

    def test_object_list_response(self):
        """Test object list response structure."""
        data = {
            "objects": [
                {
                    "id": "obj-1",
                    "payload": {
                        "title": "Object 1",
                        "object_type": "note",
                    },
                    "vector": [0.1] * 384,
                }
            ],
            "total": 1,
        }

        response = ObjectListResponse(**data)

        assert len(response.objects) == 1
        assert response.total == 1


@pytest.mark.asyncio
class TestBlockModels:
    """Test cases for block Pydantic models."""

    def test_block_properties_valid(self):
        """Test creating valid block properties."""
        data = {
            "checked": True,
            "language": "python",
            "collapsed": False,
            "priority": "high",
        }

        props = BlockProperties(**data)

        assert props.checked is True
        assert props.language == "python"
        assert props.collapsed is False
        assert props.priority == "high"

    def test_block_create_valid(self):
        """Test creating block with BlockCreate model."""
        data = {
            "object_id": "obj-1",
            "content": "New block",
            "type": "text",
        }

        block = BlockCreate(**data)

        assert block.object_id == "obj-1"
        assert block.content == "New block"
        assert block.type == "text"

    def test_block_create_checklist(self):
        """Test creating checklist block."""
        data = {
            "object_id": "obj-1",
            "content": "Checklist item",
            "type": "text",
            "properties": {"checked": False},
        }

        block = BlockCreate(**data)

        assert block.properties.checked is False

    def test_block_create_code(self):
        """Test creating code block."""
        data = {
            "object_id": "obj-1",
            "content": "print('hello')",
            "type": "code",
            "properties": {"language": "python"},
        }

        block = BlockCreate(**data)

        assert block.properties.language == "python"

    def test_block_update_partial(self):
        """Test updating block with partial data."""
        data = {
            "content": "Updated content",
        }

        block = BlockUpdate(**data)

        assert block.content == "Updated content"


@pytest.mark.asyncio
class TestTaskModels:
    """Test cases for task Pydantic models."""

    def test_task_status_enum(self):
        """Test task status enum values."""
        assert TaskStatus.TODO == "todo"
        assert TaskStatus.IN_PROGRESS == "in-progress"
        assert TaskStatus.BLOCKED == "blocked"
        assert TaskStatus.REVIEW == "review"
        assert TaskStatus.DONE == "done"

    def test_priority_enum(self):
        """Test priority enum values."""
        assert Priority.LOW == "low"
        assert Priority.MEDIUM == "medium"
        assert Priority.HIGH == "high"
        assert Priority.URGENT == "urgent"

    def test_task_create_valid(self):
        """Test creating task with TaskCreate model."""
        data = {
            "title": "Test Task",
            "content": "Task description",
            "priority": Priority.MEDIUM,
        }

        task = TaskCreate(**data)

        assert task.title == "Test Task"
        assert task.priority == Priority.MEDIUM
        assert task.content == "Task description"

    def test_task_create_minimal(self):
        """Test creating task with minimal fields."""
        data = {
            "title": "Minimal Task",
        }

        task = TaskCreate(**data)

        assert task.title == "Minimal Task"
        assert task.priority == Priority.MEDIUM  # Default value

    def test_task_update_status(self):
        """Test updating task status."""
        data = {
            "status": TaskStatus.IN_PROGRESS,
        }

        task = TaskUpdate(**data)

        assert task.status == TaskStatus.IN_PROGRESS

    def test_task_update_multiple_fields(self):
        """Test updating multiple task fields."""
        data = {
            "title": "Updated title",
            "status": TaskStatus.DONE,
            "priority": Priority.HIGH,
        }

        task = TaskUpdate(**data)

        assert task.title == "Updated title"
        assert task.status == TaskStatus.DONE


@pytest.mark.asyncio
class TestRelationModels:
    """Test cases for relation Pydantic models."""

    def test_relation_create_valid(self):
        """Test creating relation with RelationCreate model."""
        data = {
            "source_type": "object",
            "source_id": "obj-1",
            "target_type": "object",
            "target_id": "obj-2",
            "relation_type": "references",
        }

        relation = RelationCreate(**data)

        assert relation.source_type == "object"
        assert relation.source_id == "obj-1"
        assert relation.target_type == "object"
        assert relation.target_id == "obj-2"
        assert relation.relation_type == "references"

    def test_relation_create_bidirectional(self):
        """Test creating bidirectional relation."""
        data1 = {
            "source_type": "object",
            "source_id": "obj-1",
            "target_type": "object",
            "target_id": "obj-2",
            "relation_type": "references",
        }

        data2 = {
            "source_type": "object",
            "source_id": "obj-2",
            "target_type": "object",
            "target_id": "obj-1",
            "relation_type": "referenced_by",
        }

        rel1 = RelationCreate(**data1)
        rel2 = RelationCreate(**data2)

        assert rel1.source_id == "obj-1"
        assert rel2.source_id == "obj-2"

    def test_relation_update(self):
        """Test updating relation."""
        data = {
            "relation_type": "depends_on",
        }

        relation = RelationUpdate(**data)

        assert relation.relation_type == "depends_on"

    def test_relation_list_response(self):
        """Test relation list response."""
        data = {
            "relations": [
                {
                    "id": "rel-1",
                    "payload": {
                        "source_type": "object",
                        "source_id": "obj-1",
                        "target_type": "object",
                        "target_id": "obj-2",
                        "relation_type": "references",
                    },
                    "vector": [0.1] * 384,
                }
            ],
        }

        response = RelationListResponse(**data)

        assert len(response.relations) == 1


@pytest.mark.asyncio
class TestModelValidation:
    """Test cases for general model validation."""

    def test_url_validation(self):
        """Test properties store arbitrary string fields."""
        data = {
            "title": "Test",
            "type": "note",
            "properties": {
                "tags": [],
                "notes": "some url: https://example.com",
            },
        }

        obj = ObjectCreate(**data)
        assert "example.com" in obj.properties.notes

    def test_datetime_validation(self):
        """Test datetime field validation."""
        data = {
            "tags": [],
            "created_at": "invalid-datetime",
        }

        # Datetime is stored as string, no validation
        props = ObjectProperties(**data)
        assert props.created_at == "invalid-datetime"

    def test_array_validation(self):
        """Test array/list field validation."""
        data = {
            "title": "Test",
            "type": "note",
            "properties": {
                "tags": "not-an-array",
            },
        }

        # Tags in properties should be a list
        with pytest.raises(ValidationError):
            ObjectProperties(tags="not-an-array")

    def test_enum_validation(self):
        """Test enum field validation."""
        data = {
            "title": "Test Task",
            "priority": "invalid_priority",
        }

        # Priority enum validates
        with pytest.raises(ValidationError):
            TaskCreate(**data)

    def test_integer_validation(self):
        """Test integer field validation."""
        data = {
            "tags": [],
            "rating": "not-an-integer",
        }

        # Rating should be an integer or None
        with pytest.raises(ValidationError):
            ObjectProperties(**data)

    def test_boolean_validation(self):
        """Test boolean field validation."""
        data = {
            "tags": [],
            "is_watched": "not-a-boolean",
        }

        # is_watched should be a boolean or None
        with pytest.raises(ValidationError):
            ObjectProperties(**data)
