# Knowledge OS Frontend Test Suite

This directory contains the comprehensive test suite for the Knowledge OS frontend.

## Test Structure

- `src/test/setup.ts` - Test setup and global mocks
- `src/lib/__tests__/utils.test.ts` - Tests for utility functions
- `src/services/__tests__/api.test.ts` - Tests for API service layer
- `src/stores/__tests__/websocket.test.ts` - Tests for WebSocket store
- `src/hooks/__tests__/useWebSocket.test.ts` - Tests for WebSocket hook
- `src/components/__tests__/ErrorBoundary.test.tsx` - Tests for ErrorBoundary component

## Running Tests

First, install test dependencies:

```bash
cd frontend
npm install
```

Run all tests:

```bash
npm test
```

Run tests in watch mode:

```bash
npm run test:watch
```

Run tests with coverage:

```bash
npm run test:coverage
```

Run specific test file:

```bash
npx vitest src/lib/__tests__/utils.test.ts
```

## Test Configuration

Tests are configured in `vitest.config.ts`:

- Uses jsdom environment
- Sets up test globals
- Configures coverage reporting with 80% target
- Extends Vitest's expect with jest-dom matchers

## Writing Tests

### Component Tests

```tsx
import { render, screen } from '@testing-library/react'
import { expect, test } from 'vitest'
import MyComponent from '../MyComponent'

test('renders component', () => {
  render(<MyComponent />)
  expect(screen.getByText('Hello')).toBeInTheDocument()
})
```

### Hook Tests

```ts
import { renderHook } from '@testing-library/react'
import { expect, test } from 'vitest'
import useMyHook from '../useMyHook'

test('hook returns correct value', () => {
  const { result } = renderHook(() => useMyHook())
  expect(result.current).toBe('expected value')
})
```

### API Tests

```ts
import { vi, expect, test } from 'vitest'
import { objectsApi } from '../api'
import axios from 'axios'

vi.mock('axios')

test('should list objects', async () => {
  vi.mocked(axios.get).mockResolvedValue({ data: { objects: [], total: 0 } })
  const result = await objectsApi.list()
  expect(result.objects).toEqual([])
})
```

## Notes

- Tests use jsdom for DOM simulation
- Vitest is used as the test runner (not Jest)
- @testing-library/react is used for component testing
- All external dependencies (axios, WebSocket) are mocked
- Coverage target is >80% for all modules
