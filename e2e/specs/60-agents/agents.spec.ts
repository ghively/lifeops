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
    await newAgentBtn.click()
    await page.waitForTimeout(800)
    // After clicking, expect either a dialog or a form-like surface.
    const formSurface = page
      .locator('[role="dialog"], form, input[name*="name" i]')
      .first()
    expect(await formSurface.count()).toBeGreaterThan(0)
  })
})
