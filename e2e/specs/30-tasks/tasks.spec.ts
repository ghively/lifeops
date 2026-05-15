import { test, expect } from '@playwright/test'
import { captureBrowserLogs } from '../../helpers/console'
import { FRONTEND_URL } from '../../helpers/env'

test.describe('Tasks page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/tasks`)
    await page.waitForLoadState('networkidle').catch(() => {})
  })

  test('renders the tasks page without throwing', async ({ page }) => {
    const cap = captureBrowserLogs(page)
    await page.waitForTimeout(500)
    expect(page.url()).toContain('/tasks')
    cap.detach()
    expect(cap.logs.filter((l) => l.type === 'pageerror')).toEqual([])
  })

  test('task creation control is reachable', async ({ page }) => {
    const createBtn = page
      .getByRole('button', { name: /new task|create|add/i })
      .first()
    const taskInput = page
      .getByPlaceholder(/title|task|what needs/i)
      .first()
    const visible =
      (await createBtn.isVisible().catch(() => false)) ||
      (await taskInput.isVisible().catch(() => false))
    expect(visible, 'no task creation control found').toBe(true)
  })

  test('can create a task via the UI (best-effort)', async ({ page }) => {
    const titleField = page
      .getByPlaceholder(/title|task|what needs/i)
      .first()

    if (await titleField.isVisible().catch(() => false)) {
      const title = `e2e task ${Date.now()}`
      await titleField.fill(title)
      // Submitting via Enter avoids races with the inline "Add" button's
      // disabled state (it stays disabled until the title is non-empty and
      // React has re-rendered, which can lag behind fill()).
      await titleField.press('Enter')
      await page.waitForTimeout(1500)
      await expect(page.locator(`text=${title}`).first()).toBeVisible({
        timeout: 5000,
      })
    } else {
      test.skip(true, 'no task creation form visible')
    }
  })

  test('task list area is rendered', async ({ page }) => {
    // The list is a div container (data-testid="task-row" per row) or, when
    // empty, the page renders a "No tasks found" empty state. Either is an
    // acceptable "list area rendered" signal.
    const taskRow = page.locator('[data-testid="task-row"]')
    const emptyState = page.getByText(/no tasks found/i)
    const hasRows = (await taskRow.count()) > 0
    const hasEmpty = await emptyState.isVisible().catch(() => false)
    expect(hasRows || hasEmpty).toBe(true)
  })
})
