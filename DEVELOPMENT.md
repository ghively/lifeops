# Development Guide

Instructions for contributing to Knowledge OS development.

---

## Table of Contents

1. [Getting Started](#getting-started)
2. [Development Workflow](#development-workflow)
3. [Backend Development](#backend-development)
4. [Frontend Development](#frontend-development)
5. [Testing](#testing)
6. [Code Standards](#code-standards)
7. [Git Workflow](#git-workflow)
8. [Troubleshooting](#troubleshooting)

---

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+
- Git
- Docker (recommended)
- IDE: VS Code, PyCharm, or similar

### Clone and Setup

```bash
git clone https://github.com/ghively/knowledge-os.git
cd knowledge-os

# Create feature branch
git checkout -b feature/your-feature

# Backend setup
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Frontend setup
cd ../frontend
npm install
```

---

## Development Workflow

### 1. Start Services

**Terminal 1: Backend**
```bash
cd backend
source venv/bin/activate
python -m uvicorn app.main:app --reload --port 8000
```

**Terminal 2: Frontend**
```bash
cd frontend
npm run dev
```

**Terminal 3: Qdrant**
```bash
docker run -p 6333:6333 qdrant/qdrant
```

**Terminal 4: Ollama (optional)**
```bash
ollama serve
```

### 2. Test Changes

```bash
# Run test suite
pytest backend/tests/

# Frontend tests
cd frontend && npm test

# E2E tests
cd e2e && npm test
```

### 3. Commit and Push

```bash
git add .
git commit -m "feat: Add new feature"
git push origin feature/your-feature
```

### 4. Create Pull Request

- Go to GitHub
- Create PR against `main`
- Fill in description
- Request review

---

## Backend Development

### Project Structure

```
backend/
├─ app/
│  ├─ main.py            # FastAPI app
│  ├─ config.py          # Configuration
│  ├─ routers/           # API routes
│  ├─ services/          # Business logic
│  ├─ models/            # Data models
│  ├─ database/          # DB clients
│  ├─ middleware/        # Middleware
│  └─ utils/             # Utilities
├─ tests/                # Test suite
├─ alembic/              # Database migrations
├─ pyproject.toml        # Project config
└─ requirements.txt      # Dependencies
```

### Adding an Endpoint

1. **Create router** (`routers/feature.py`):

```python
from fastapi import APIRouter, Depends
from app.middleware.auth import get_current_user

router = APIRouter()

@router.get("/feature")
async def get_feature(
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Get feature data."""
    return {"feature": "data"}
```

2. **Register router** (`main.py`):

```python
from app.routers import feature
app.include_router(
    feature.router,
    prefix="/api/v1/feature",
    tags=["feature"]
)
```

3. **Add tests** (`tests/test_feature.py`):

```python
async def test_get_feature(async_client):
    response = await async_client.get("/api/v1/feature")
    assert response.status_code == 200
```

### Running Tests

```bash
# All tests
pytest

# Specific file
pytest tests/test_auth.py

# Specific test
pytest tests/test_auth.py::test_login

# Verbose output
pytest -v

# With coverage
pytest --cov=app

# Watch mode
pytest-watch
```

### Database Migrations

```bash
# Create migration
alembic revision --autogenerate -m "Add new column"

# Review migration
cat alembic/versions/0002_add_new_column.py

# Apply migration
alembic upgrade head

# Downgrade
alembic downgrade -1
```

### Debugging

**VS Code Launch Config** (`.vscode/launch.json`):

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "FastAPI",
      "type": "python",
      "request": "launch",
      "module": "uvicorn",
      "args": ["app.main:app", "--reload"],
      "cwd": "${workspaceFolder}/backend"
    }
  ]
}
```

**Add breakpoints and debug in IDE.**

---

## Frontend Development

### Project Structure

```
frontend/
├─ src/
│  ├─ components/       # React components
│  ├─ pages/           # Page components
│  ├─ hooks/           # Custom hooks
│  ├─ stores/          # Zustand stores
│  ├─ services/        # API client
│  ├─ lib/             # Utilities
│  ├─ App.tsx          # Root component
│  └─ index.css        # Global styles
├─ public/             # Static assets
├─ tests/              # Test files
├─ vite.config.ts      # Vite config
└─ package.json        # Dependencies
```

### Adding a Component

1. **Create component** (`components/Feature.tsx`):

```typescript
import { useState } from 'react'

interface FeatureProps {
  title: string
  onDone?: () => void
}

export function Feature({ title, onDone }: FeatureProps) {
  const [status, setStatus] = useState('idle')

  return (
    <div className="feature">
      <h2>{title}</h2>
      <p>Status: {status}</p>
      <button onClick={onDone}>Done</button>
    </div>
  )
}
```

2. **Use component** in parent:

```typescript
import { Feature } from '@/components/Feature'

<Feature title="My Feature" onDone={() => console.log('done')} />
```

3. **Add tests** (`components/__tests__/Feature.test.tsx`):

```typescript
import { render, screen } from '@testing-library/react'
import { Feature } from '../Feature'

test('renders feature', () => {
  render(<Feature title="Test" />)
  expect(screen.getByText('Test')).toBeInTheDocument()
})
```

### Running Tests

```bash
# All tests
npm test

# Watch mode
npm test -- --watch

# Coverage
npm test -- --coverage

# Specific file
npm test Feature
```

### Building

```bash
# Development build (watch)
npm run dev

# Production build
npm run build

# Preview production build
npm run preview

# Type checking
npm run typecheck
```

---

## Testing

### Backend Test Example

```python
# tests/test_agents.py
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

@pytest.fixture
async def auth_headers(db):
    """Create user and return auth headers."""
    user = await create_test_user(db)
    token = create_access_token(user.id)
    return {"Authorization": f"Bearer {token}"}

async def test_list_agents(auth_headers):
    response = client.get("/api/v1/agents", headers=auth_headers)
    assert response.status_code == 200
    assert "agents" in response.json()
```

### Frontend Test Example

```typescript
// src/components/__tests__/Sidebar.test.tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Sidebar } from '../Sidebar'

test('toggles sidebar', async () => {
  render(<Sidebar collapsed={false} onToggle={vi.fn()} />)
  
  const button = screen.getByRole('button', { name: /toggle/i })
  await userEvent.click(button)
  
  expect(button).toBeInTheDocument()
})
```

### E2E Test Example

```typescript
// e2e/tests/auth.spec.ts
import { test, expect } from '@playwright/test'

test('user can login', async ({ page }) => {
  await page.goto('http://localhost:5173')
  
  await page.fill('input[name="email"]', 'test@example.com')
  await page.fill('input[name="password"]', 'password123')
  await page.click('button[type="submit"]')
  
  await expect(page).toHaveURL('/notes')
})
```

---

## Code Standards

### Python

- **Style**: PEP 8, use `black` for formatting
- **Typing**: Type hints on all functions
- **Docstrings**: Module, class, and public function docstrings
- **Imports**: Sorted with `isort`

```python
# Format check
black --check backend/

# Format code
black backend/

# Check types
mypy backend/app/
```

### TypeScript

- **Style**: Prettier for formatting
- **Linting**: ESLint
- **Typing**: Full type coverage (no `any`)

```bash
# Check format
npm run lint

# Format code
npm run format

# Type check
npm run typecheck
```

### Naming Conventions

**Backend:**
- Classes: `PascalCase` (e.g., `AgentLoop`)
- Functions: `snake_case` (e.g., `get_agent_status`)
- Constants: `UPPER_CASE` (e.g., `MAX_ITERATIONS`)
- Private: `_leading_underscore` (e.g., `_internal_method`)

**Frontend:**
- Components: `PascalCase` (e.g., `AgentChatPanel`)
- Functions: `camelCase` (e.g., `getAgentStatus`)
- Constants: `UPPER_CASE` (e.g., `MAX_ITERATIONS`)
- File names: Match export name or use `index.tsx`

### Comments

- Only comment the **why**, not the what
- Keep comments up-to-date with code
- Use TODO/FIXME sparingly (track in issues instead)

---

## Git Workflow

### Branch Naming

```
feature/description      - New feature
fix/description          - Bug fix
docs/description         - Documentation
refactor/description     - Code refactoring
test/description         - Test improvements
```

### Commit Messages

```
feat: Add new feature description
fix: Fix bug description
docs: Update documentation
refactor: Refactor component name
test: Add tests for feature
chore: Update dependencies
```

### Pull Request Process

1. **Create branch** from `main`
2. **Make changes** with clear commits
3. **Push** to GitHub
4. **Create PR** with:
   - Clear title
   - Description of changes
   - Link to related issues
   - Screenshots for UI changes
5. **Address review** comments
6. **Merge** when approved and CI passes

---

## CI/CD Pipeline

Tests run automatically on PR:

```
1. Lint checks (Backend + Frontend)
2. Type checking
3. Unit tests
4. Integration tests
5. E2E tests (if changed)
6. Security scanning (if enabled)
```

View status in GitHub PR page.

---

## Troubleshooting

### Import Errors

```python
# ModuleNotFoundError
# Solution: Activate venv
source venv/bin/activate
pip install -r requirements.txt
```

### Port Already in Use

```bash
# Backend already running?
lsof -i :8000
kill -9 <pid>

# Or use different port
uvicorn app.main:app --port 8001
```

### Test Failures

```bash
# Clear cache
pytest --cache-clear

# Verbose output
pytest -vv

# Run single test
pytest tests/test_auth.py::test_login -vv
```

### Type Checking Errors

```bash
# Install types
pip install types-requests types-redis

# Check
mypy backend/app/
```

---

## Performance Optimization

### Backend

```python
# Use async/await for I/O
async def get_data():
    result = await db.query()
    return result

# Batch database operations
objects = session.query(Object).filter(...).all()

# Cache frequently accessed data
@lru_cache(maxsize=128)
def get_config():
    ...
```

### Frontend

```typescript
// Memoize expensive calculations
const MemoComponent = memo(function Component(props) {
  // ...
})

// Lazy load components
const Component = lazy(() => import('./Component'))

// Use virtualization for large lists
<VirtualList items={items} itemHeight={50} />
```

---

## Resources

- **FastAPI Docs**: https://fastapi.tiangolo.com
- **React Docs**: https://react.dev
- **TypeScript**: https://www.typescriptlang.org
- **Qdrant**: https://qdrant.tech/documentation
- **Testing**: https://docs.pytest.org, https://testing-library.com

---

**Ready to contribute!** See [CONTRIBUTING.md](CONTRIBUTING.md) for more details.
