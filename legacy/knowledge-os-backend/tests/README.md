# Knowledge OS Test Suite

This directory contains the comprehensive test suite for the Knowledge OS backend.

## Test Structure

- `conftest.py` - Shared pytest fixtures for mocking Qdrant, SQLite, embedding service, etc.
- `test_objects.py` - Tests for objects CRUD operations
- `test_blocks.py` - Tests for blocks CRUD operations
- `test_relations.py` - Tests for relations CRUD and service
- `test_search.py` - Tests for semantic and exact search
- `test_tasks.py` - Tests for task management
- `test_files.py` - Tests for file management and watching
- `test_agents.py` - Tests for agent communication
- `test_settings.py` - Tests for settings management
- `test_websocket.py` - Tests for WebSocket manager
- `test_embedding.py` - Tests for embedding service
- `test_models.py` - Tests for Pydantic model validation
- `test_utils.py` - Tests for utility functions
- `test_services.py` - Tests for backend services

## Running Tests

First, install test dependencies:

```bash
pip install -r requirements.txt
```

Run all tests:

```bash
cd backend
python -m pytest tests/ -v
```

Run with coverage:

```bash
python -m pytest tests/ --cov=app --cov-report=html
```

Run specific test file:

```bash
python -m pytest tests/test_objects.py -v
```

Run specific test:

```bash
python -m pytest tests/test_objects.py::TestObjectsRouter::test_list_objects_empty -v
```

## Test Fixtures

The test suite uses the following fixtures (defined in `conftest.py`):

- `mock_qdrant_client` - Mock Qdrant client with in-memory storage
- `mock_async_qdrant_client` - Mock async Qdrant client
- `mock_sqlite_manager` - Mock SQLite database manager
- `mock_embedding_service` - Mock embedding service with deterministic vectors
- `mock_websocket_manager` - Mock WebSocket connection manager
- `mock_openclaw_service` - Mock OpenClaw gateway service
- `test_client` - HTTPX AsyncClient with mocked dependencies
- `sample_object_data` - Sample object data for testing
- `sample_block_data` - Sample block data for testing
- `sample_task_data` - Sample task data for testing
- `sample_relation_data` - Sample relation data for testing

## Notes

- All tests use mocks and don't require external services (Qdrant, OpenClaw, etc.)
- Tests use `pytest-asyncio` for async test support
- Coverage target is >80% for all modules
- Tests are organized by feature (router tests, service tests, model tests)
