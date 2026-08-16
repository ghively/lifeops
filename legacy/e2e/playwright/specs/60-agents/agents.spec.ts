import { test, expect } from '@playwright/test'
import { captureBrowserLogs } from '../../helpers/console'
import { FRONTEND_URL } from '../../helpers/env'

test.describe('Agents page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/agents`)
    await page.waitForLoadState('networkidle').catch(() => {})
  })

  test('renders without throwing', async ({ page }) => {
    const cap = captureBrowserLogs(page)
    await page.waitForTimeout(500)
    cap.detach()
    expect(cap.logs.filter((l) => l.type === 'pageerror')).toEqual([])
  })

  test('exposes a way to create or open an agent', async ({ page }) => {
    const newAgentBtn = page
      .getByRole('button', { name: /new agent|create agent|add agent/i })
      .first()
    const anyAgentLink = page.locator('a[href*="/agents/"]').first()
    const visible =
      (await newAgentBtn.isVisible().catch(() => false)) ||
      (await anyAgentLink.isVisible().catch(() => false))
    expect(visible, 'no agent affordance on /agents').toBe(true)
  })

  test('agent creation flow is reachable (best-effort)', async ({ page }) => {
    const newAgentBtn = page
      .getByRole('button', { name: /new agent|create agent|add agent/i })
      .first()
    if (!(await newAgentBtn.isVisible().catch(() => false))) {
      test.skip(true, 'no create-agent button visible')
    }
    // The "New Agent" button is disabled until an agent id is provided.
    // The page exposes that input inline — fill it so the affordance becomes
    // reachable, then verify the button enables (not the click outcome).
    const idInput = page.getByPlaceholder(/new-agent-id|agent id/i).first()
    if (await idInput.isVisible().catch(() => false)) {
      await idInput.fill(`e2e-agent-${Date.now()}`)
    }
    await expect(newAgentBtn).toBeEnabled({ timeout: 5_000 })
  })
})
