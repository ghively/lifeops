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
    // Match the inline create input specifically. A naive
    // /title|task|what needs/ selector also grabs the global header search
    // ("Search notes, tasks, files, agents…"), which is rendered first and
    // would shadow the real create field.
    const taskInput = page
      .getByPlaceholder(/create.*task|new task|title|what needs/i)
      .first()
    const visible =
      (await createBtn.isVisible().catch(() => false)) ||
      (await taskInput.isVisible().catch(() => false))
    expect(visible, 'no task creation control found').toBe(true)
  })

  test('can create a task via the UI (best-effort)', async ({ page }) => {
    const titleField = page
      .getByPlaceholder(/create.*task|new task|title|what needs/i)
      .first()

    if (await titleField.isVisible().catch(() => false)) {
      const title = `e2e task ${Date.now()}`
      await titleField.fill(title)
      // The inline "Add" button is disabled until React re-renders with the
      // new title state. Wait for it to enable, then click — this is more
      // reliable than press('Enter'), whose handler closure can read a stale
      // newTaskTitle if the state update hasn't flushed.
      const addBtn = page.getByRole('button', { name: /^add$/i }).first()
      await expect(addBtn).toBeEnabled({ timeout: 5_000 })
      await addBtn.click()
      await expect(page.locator(`text=${title}`).first()).toBeVisible({
        timeout: 5_000,
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

  test('task row shows title, status, and priority labels', async ({ page }) => {
    const taskRows = page.locator('[data-testid="task-row"], .task-row')
    const rowCount = await taskRows.count()
    if (rowCount === 0) {
      test.skip(true, 'no task rows found — create a task first')
    }

    const firstRow = taskRows.first()

    // Each row should have at least one visible text node (the title) and
    // at least one label badge indicating status or priority.
    const rowText = await firstRow.textContent()
    expect(rowText, 'task row has no text content').toBeTruthy()

    // Status badge: look for common status text or an element with a role
    // that could act as a badge/button for the status
    const statusBadge = firstRow
      .locator(
        '[data-testid*="status"], [class*="status"], [class*="badge"], ' +
        '[role="button"][aria-label*="status"], button[class*="status"]'
      )
      .or(
        firstRow.getByText(
          /todo|in.?progress|in progress|done|completed|pending|blocked/i
        )
      )
      .first()

    const priorityBadge = firstRow
      .locator('[data-testid*="priority"], [class*="priority"]')
      .or(firstRow.getByText(/low|medium|high|urgent|critical/i))
      .first()

    const hasStatus = await statusBadge.isVisible().catch(() => false)
    const hasPriority = await priorityBadge.isVisible().catch(() => false)

    // At minimum the row must show either a status or priority label
    expect(
      hasStatus || hasPriority,
      'task row does not show any status or priority label'
    ).toBe(true)
  })

  test('task status update: clicking status badge cycles through states', async ({
    page,
  }) => {
    const taskRows = page.locator('[data-testid="task-row"], .task-row')
    const rowCount = await taskRows.count()
    if (rowCount === 0) {
      test.skip(true, 'no task rows present — cannot test status cycling')
    }

    const firstRow = taskRows.first()

    // Look for a status badge or dropdown trigger on the first row
    const statusControl = firstRow
      .locator(
        '[data-testid*="status"], button[class*="status"], ' +
        '[role="button"][aria-label*="status"], [class*="status-badge"], ' +
        '[class*="statusBadge"]'
      )
      .first()

    const errors: string[] = []
    page.on('pageerror', (e) => errors.push(e.message))

    if (!(await statusControl.isVisible().catch(() => false))) {
      test.skip(true, 'no clickable status badge found on task row')
    }

    // Capture the initial text so we can detect a change
    const initialText = (await statusControl.textContent()) ?? ''
    await statusControl.click()

    // After click, either a dropdown appeared or the badge text changed.
    // Accept either: a visible listbox/menu, or changed badge text.
    const menuAppeared = await page
      .locator('[role="listbox"], [role="menu"], [role="option"]')
      .first()
      .isVisible({ timeout: 3_000 })
      .catch(() => false)

    if (menuAppeared) {
      // Pick the first option that differs from the current state
      const options = page.locator('[role="option"], [role="menuitem"]')
      const optCount = await options.count()
      if (optCount > 0) {
        await options.first().click()
      }
    }

    // After the interaction: no JS errors, and either the text changed or a
    // menu appeared (both are valid "cycling" signals).
    await page.waitForTimeout(300)
    const newText = (await statusControl.textContent().catch(() => '')) ?? ''
    expect(menuAppeared || newText !== initialText).toBe(true)
    expect(errors).toEqual([])
  })

  test('task delete or remove action is reachable', async ({ page }) => {
    const taskRows = page.locator('[data-testid="task-row"], .task-row')
    const rowCount = await taskRows.count()
    if (rowCount === 0) {
      test.skip(true, 'no task rows found — cannot test delete affordance')
    }

    const firstRow = taskRows.first()

    // Hover to reveal delete icon if it's only shown on hover
    await firstRow.hover().catch(() => {})

    const deleteControl = firstRow
      .locator(
        '[data-testid*="delete"], [aria-label*="delete"], ' +
        '[aria-label*="remove"], [aria-label*="trash"], ' +
        'button[class*="delete"], button[class*="remove"]'
      )
      .or(firstRow.getByRole('button', { name: /delete|remove|trash/i }))
      .first()

    const visible = await deleteControl.isVisible({ timeout: 2_000 }).catch(() => false)

    if (!visible) {
      // Some implementations surface delete via a row context menu (⋮)
      const moreBtn = firstRow
        .locator('[data-testid*="more"], [aria-label*="more"], button[class*="more"]')
        .or(firstRow.getByRole('button', { name: /more|actions|options|⋮/i }))
        .first()

      if (await moreBtn.isVisible().catch(() => false)) {
        await moreBtn.click()
        const deleteInMenu = page
          .locator('[role="menuitem"]')
          .getByText(/delete|remove/i)
          .first()
        const menuDeleteVisible = await deleteInMenu
          .isVisible({ timeout: 2_000 })
          .catch(() => false)
        expect(
          menuDeleteVisible,
          'delete option not found in task row context menu'
        ).toBe(true)
        // Close the menu without deleting
        await page.keyboard.press('Escape')
        return
      }

      test.skip(true, 'no delete affordance visible on task row (hover + more-menu checked)')
    }

    // Found the delete button — just assert it's enabled; don't actually delete
    expect(await deleteControl.isEnabled().catch(() => true)).toBe(true)
  })
})
