# Contributing to Knowledge OS

Thank you for your interest in contributing to Knowledge OS! This document provides guidelines and instructions for contributing.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Making Changes](#making-changes)
- [Submitting Changes](#submitting-changes)
- [Coding Standards](#coding-standards)
- [Commit Messages](#commit-messages)

## Code of Conduct

This project adheres to a code of conduct. By participating, you are expected to uphold this code:

- Be respectful and inclusive
- Welcome newcomers
- Focus on constructive feedback
- Respect different viewpoints and experiences

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/yourusername/knowledge-os.git`
3. Create a branch for your changes: `git checkout -b feature/your-feature-name`

## Development Setup

### Prerequisites

- Docker & Docker Compose
- Node.js 20+ (for frontend development)
- Python 3.11+ (for backend development)

### Running Locally

```bash
# Start all services
docker-compose up -d

# Or run services individually for development
# Frontend
cd frontend && npm install && npm run dev

# Backend
cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload
```

## Making Changes

### Branch Naming

- `feature/description` - New features
- `bugfix/description` - Bug fixes
- `docs/description` - Documentation updates
- `refactor/description` - Code refactoring
- `test/description` - Test additions/updates

### Before Submitting

1. **Test your changes**
   ```bash
   # Backend
   cd backend && pytest

   # Frontend
   cd frontend && npm test

   # E2E (with backend + frontend running locally — always exits 0,
   # writes the result punch list to e2e/REPORT.md):
   cd e2e && bash scripts/run-suite.sh
   ```

2. **Update documentation**
   - Update README.md if user-facing
   - Update the relevant top-level doc (API.md, AUTH.md, AGENT_SYSTEM.md, etc.)
   - Add an entry to CHANGELOG.md under `[Unreleased]`

3. **Check code quality**
   ```bash
   # Frontend
   cd frontend && npm run lint && npx tsc --noEmit

   # Backend (formatting via black; isort for import ordering):
   cd backend && black --check . && isort --check-only .
   ```

## Submitting Changes

### Pull Request Process

1. Update your fork with the latest main branch
2. Push your branch to your fork
3. Create a Pull Request against the main repository
4. Fill out the PR template completely
5. Link any related issues
6. Wait for review and address feedback

### PR Requirements

- [ ] All tests pass
- [ ] Code follows style guidelines
- [ ] Documentation is updated
- [ ] No merge conflicts
- [ ] PR description is complete

## Coding Standards

### Frontend (TypeScript/React)

- Use functional components with hooks
- Follow the existing component structure
- Use TypeScript strict mode
- Use Tailwind CSS for styling
- Follow shadcn/ui patterns for UI components

```typescript
// Good example
interface ButtonProps {
  onClick: () => void;
  children: React.ReactNode;
  disabled?: boolean;
}

export function Button({ onClick, children, disabled }: ButtonProps) {
  return (
    <button 
      onClick={onClick} 
      disabled={disabled}
      className="px-4 py-2 bg-primary text-white rounded"
    >
      {children}
    </button>
  );
}
```

### Backend (Python/FastAPI)

- Follow PEP 8 style guide
- Use type hints
- Write docstrings for functions and classes
- Keep functions focused and small
- Use async/await for I/O operations

```python
# Good example
from typing import Optional
from fastapi import HTTPException

async def get_object_by_id(object_id: str) -> Optional[Object]:
    """Retrieve an object by its ID.
    
    Args:
        object_id: The unique identifier of the object
        
    Returns:
        The object if found, None otherwise
        
    Raises:
        HTTPException: If the object ID is invalid
    """
    if not object_id:
        raise HTTPException(status_code=400, detail="Invalid object ID")
    
    return await db.objects.find_one({"id": object_id})
```

## Commit Messages

Use conventional commits format:

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, etc.)
- `refactor`: Code refactoring
- `test`: Test additions/updates
- `chore`: Build process, dependencies, etc.

Examples:
```
feat(blocks): add support for code blocks

fix(search): resolve issue with empty query results

docs(api): update authentication documentation
```

## Questions?

- Open an issue for questions
- Join discussions in existing issues

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
