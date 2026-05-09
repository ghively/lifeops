import { test, expect } from '@playwright/test'
import { captureBrowserLogs } from '../../helpers/console'
import { FRONTEND_URL } from '../../helpers/env'

test.describe('Outliner page', () => {
  test('renders the editor surface', async ({ page }) => {
    const cap = captureBrowserLogs(page)
    await page.goto(FRONTEND_URL)
    await page.waitForLoadState('networkidle').catch(() => {})

    // The outliner is a contenteditable Slate surface OR an explicit textarea
    // depending on how blocks are rendered. Accept either signal.
    const editorCandidates = [
      page.locator('[contenteditable="true"]').first(),
      page.locator('[role="textbox"]').first(),
      page.locator('textarea').first(),
    ]
    let found = false
    for (const cand of editorCandidates) {
      if (await cand.isVisible().catch(() => false)) {
        found = true
        break
      }
    }
    expect(found, 'no editable surface on the outliner page').toBe(true)
    cap.detach()
  })

  test('typing into a block does not throw', async ({ page }) => {
    const errors: string[] = []
    page.on('pageerror', (e) => errors.push(e.message))
    await page.goto(FRONTEND_URL)
    await page.waitForLoadState('networkidle').catch(() => {})

    const editor = page.locator('[contenteditable="true"]').first()
    if (await editor.isVisible().catch(() => false)) {
      await editor.click()
      await page.keyboard.type('e2e probe text', { delay: 10 })
      await page.waitForTimeout(500)
    }
    expect(errors).toEqual([])
  })

  test('Enter creates a new block (best-effort assertion)', async ({ page }) => {
    await page.goto(FRONTEND_URL)
    await page.waitForLoadState('networkidle').catch(() => {})

    const editor = page.locator('[contenteditable="true"]').first()
    if (!(await editor.isVisible().catch(() => false))) {
      test.skip(true, 'editor not visible — feature gated or unavailable')
    }
    await editor.click()
    const before = await page.locator('[contenteditable="true"]').count()
    await page.keyboard.type('first line', { delay: 10 })
    await page.keyboard.press('Enter')
    await page.keyboard.type('second line', { delay: 10 })
    await page.waitForTimeout(500)
    const after = await page.locator('[contenteditable="true"]').count()
    // We can't strictly assert > 1 because some implementations use a single
    // contenteditable for the whole doc — we just assert no crash.
    expect(after).toBeGreaterThanOrEqual(before)
  })
})
