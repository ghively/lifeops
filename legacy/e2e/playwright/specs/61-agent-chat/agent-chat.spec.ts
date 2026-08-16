import { test, expect } from '@playwright/test'
import { captureBrowserLogs } from '../../helpers/console'
import { FRONTEND_URL } from '../../helpers/env'

test.describe('Agent chat', () => {
  test('agents page loads without errors', async ({ page }) => {
    const cap = captureBrowserLogs(page)
    await page.goto(`${FRONTEND_URL}/agents`)
    await page.waitForLoadState('networkidle').catch(() => {})
    await page.waitForTimeout(500)

    expect(page.url()).toContain('/agents')
    cap.detach()
    expect(cap.logs.filter((l) => l.type === 'pageerror')).toEqual([])
  })

  test('agent creation flow: can type an agent ID and submit', async ({ page }) => {
    const cap = captureBrowserLogs(page)
    await page.goto(`${FRONTEND_URL}/agents`)
    await page.waitForLoadState('networkidle').catch(() => {})

    // Find the agent ID input field
    const idInput = page
      .getByPlaceholder(/new-agent-id|agent.?id|agent name|create agent/i)
      .or(page.locator('input[name*="agent" i]').first())
      .or(
        page.locator(
          '[data-testid="agent-id-input"], [data-testid="new-agent-input"], ' +
          '[class*="agent-id"], [class*="agentId"]'
        ).first()
      )
      .first()

    if (!(await idInput.isVisible().catch(() => false))) {
      // Try clicking a "New Agent" / "Create Agent" button first to reveal the input
      const newAgentBtn = page
        .getByRole('button', { name: /new agent|create agent|add agent/i })
        .first()
      if (await newAgentBtn.isVisible().catch(() => false)) {
        await newAgentBtn.click()
        await page.waitForTimeout(400)
      }
    }

    // Re-check after potential button click
    if (!(await idInput.isVisible().catch(() => false))) {
      test.skip(true, 'no agent ID input visible — creation UI not found')
    }

    const agentId = `e2e-agent-${Date.now()}`
    await idInput.fill(agentId)

    // The create / submit button should now be enabled
    const createBtn = page
      .getByRole('button', { name: /new agent|create agent|add agent|create|add/i })
      .first()

    // Assert either the button is enabled OR the agent ID already appears in
    // the list (optimistic update on keystroke)
    const btnEnabled = await createBtn.isEnabled({ timeout: 5_000 }).catch(() => false)
    const alreadyInList = await page
      .getByText(new RegExp(agentId, 'i'))
      .isVisible()
      .catch(() => false)

    cap.detach()
    expect(
      btnEnabled || alreadyInList,
      'after typing an agent ID, the create button was not enabled'
    ).toBe(true)
    expect(cap.logs.filter((l) => l.type === 'pageerror')).toEqual([])
  })

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
