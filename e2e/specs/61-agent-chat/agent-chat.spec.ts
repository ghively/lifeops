import { test, expect } from '@playwright/test'
import { captureBrowserLogs } from '../../helpers/console'
import { FRONTEND_URL } from '../../helpers/env'

test.describe('Agent chat', () => {
  test('open agents page and follow the first chat link if present', async ({
    page,
  }) => {
    const cap = captureBrowserLogs(page)
    await page.goto(`${FRONTEND_URL}/agents`)
    await page.waitForLoadState('networkidle').catch(() => {})

    const chatLink = page
      .locator('a[href*="/chat"]')
      .or(page.getByRole('link', { name: /chat/i }))
      .first()
    if (!(await chatLink.isVisible().catch(() => false))) {
      test.skip(true, 'no agent has a chat link yet')
    }
    await chatLink.click()
    await page.waitForLoadState('networkidle').catch(() => {})
    await expect(page).toHaveURL(/\/agents\/.+\/chat/)
    cap.detach()
    expect(cap.logs.filter((l) => l.type === 'pageerror')).toEqual([])
  })

  test('chat input is interactive', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/agents`)
    await page.waitForLoadState('networkidle').catch(() => {})

    const chatLink = page.locator('a[href*="/chat"]').first()
    if (!(await chatLink.isVisible().catch(() => false))) {
      test.skip(true, 'no chat link to follow')
    }
    await chatLink.click()
    await page.waitForLoadState('networkidle').catch(() => {})

    const input = page
      .locator('textarea')
      .or(page.getByPlaceholder(/message|ask|send/i))
      .first()
    await expect(input).toBeVisible({ timeout: 10_000 })
    await input.fill('hello from e2e')
    // We do NOT actually press send — that calls a real LLM. Just confirm
    // the affordance is wired up.
    const sendBtn = page
      .getByRole('button', { name: /send|submit/i })
      .first()
    expect(await sendBtn.count()).toBeGreaterThan(0)
  })
})
