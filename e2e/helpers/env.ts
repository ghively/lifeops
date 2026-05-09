export const FRONTEND_URL = process.env.E2E_FRONTEND_URL || 'http://localhost:5173'
export const BACKEND_URL = process.env.E2E_BACKEND_URL || 'http://localhost:8000'
export const API_BASE = `${BACKEND_URL}/api/v1`

export const TEST_USER = {
  email: process.env.E2E_TEST_EMAIL || 'e2e@knowledge-os.local',
  username: process.env.E2E_TEST_USERNAME || 'e2etester',
  password: process.env.E2E_TEST_PASSWORD || 'e2eTestPass!23',
  full_name: 'E2E Test User',
}

export const AUTH_STORAGE_PATH = 'fixtures/.auth-storage.json'
