import { test, expect } from '@playwright/test'

const BASE = 'http://localhost:3010'
const TEST_EMAIL = 'e2ewalk@test.com'
const TEST_PASSWORD = 'password123'

// Auth tests run WITHOUT stored session (test the login flow itself)
test.describe('Auth', () => {
  test('1. Register page — form visible, mode toggle, register flow', async ({ page }) => {
    await page.goto(`${BASE}/login?mode=register`, { waitUntil: 'networkidle' })
    await page.waitForTimeout(500)

    await expect(page.getByPlaceholder('name@example.com').first()).toBeVisible()
    await expect(page.getByPlaceholder('johndoe')).toBeVisible()
    await expect(page.getByPlaceholder('John Doe')).toBeVisible()
    await expect(page.getByPlaceholder('Min. 8 characters').first()).toBeVisible()
    await expect(page.getByPlaceholder('Confirm your password')).toBeVisible()

    await page.getByRole('button', { name: 'Sign in' }).click()
    await expect(page.getByPlaceholder('Enter your password')).toBeVisible()

    await page.getByRole('button', { name: 'Sign up' }).click()
    await expect(page.getByPlaceholder('johndoe')).toBeVisible()

    const uniqueEmail = `e2e-reg-${Date.now()}@test.com`
    await page.getByPlaceholder('name@example.com').first().fill(uniqueEmail)
    await page.getByPlaceholder('johndoe').fill(`reguser${Date.now()}`)
    await page.getByPlaceholder('John Doe').fill('Test User')
    await page.getByPlaceholder('Min. 8 characters').first().fill('testpass123')
    await page.getByPlaceholder('Confirm your password').fill('testpass123')
    await page.getByRole('button', { name: 'Create account' }).click()
    await page.waitForTimeout(2000)

    const url = page.url()
    const onDashboard = url.endsWith('/') || url.includes('/object')
    const hasError = await page.locator('text=/Invalid|already|exists/i').count() > 0
    expect(onDashboard || hasError).toBeTruthy()
  })

  test('2. Login — fill form, submit, redirect to /', async ({ page }) => {
    await page.goto(`${BASE}/login`, { waitUntil: 'networkidle' })
    await page.waitForTimeout(500)

    await expect(page.getByPlaceholder('name@example.com').first()).toBeVisible()
    await expect(page.getByPlaceholder('Enter your password')).toBeVisible()

    await page.getByRole('link', { name: 'Forgot password?' }).click()
    await expect(page).toHaveURL(/reset-password/)

    await page.goto(`${BASE}/login`, { waitUntil: 'networkidle' })
    await page.waitForTimeout(500)
    await page.locator('input[type="email"]').fill(TEST_EMAIL)
    await page.locator('input[type="password"]').fill(TEST_PASSWORD)
    await page.getByRole('button', { name: 'Sign in' }).click()
    await page.waitForTimeout(3000)

    const url = page.url()
    expect(url === `${BASE}/` || url === `${BASE}` || url.includes('/object/')).toBeTruthy()
  })

  test('3. Reset password — request step, then confirm step', async ({ page }) => {
    await page.goto(`${BASE}/reset-password`, { waitUntil: 'networkidle' })
    await page.waitForTimeout(500)

    await expect(page.getByPlaceholder('name@example.com')).toBeVisible()
    await page.getByPlaceholder('name@example.com').fill(TEST_EMAIL)
    await page.getByRole('button', { name: 'Send reset link' }).click()
    await page.waitForTimeout(2000)

    await expect(page.getByPlaceholder(/token/i)).toBeVisible()
    await expect(page.getByPlaceholder('Min. 8 characters')).toBeVisible()
  })
})
