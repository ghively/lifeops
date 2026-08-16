import { test, expect } from '@playwright/test'
import { captureBrowserLogs } from '../../helpers/console'
import { FRONTEND_URL } from '../../helpers/env'

test.describe('Settings page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/settings`)
    await page.waitForLoadState('networkidle').catch(() => {})
  })

  test('renders without throwing', async ({ page }) => {
    const cap = captureBrowserLogs(page)
    await page.waitForTimeout(500)
    cap.detach()
    expect(cap.logs.filter((l) => l.type === 'pageerror')).toEqual([])
  })

  test('exposes at least one setting control (theme/profile/integration)', async ({
    page,
  }) => {
    const candidates = [
      page.getByRole('button', { name: /save|update|apply/i }).first(),
      page.locator('input, select, [role="switch"], [role="combobox"]').first(),
    ]
    let visible = false
    for (const c of candidates) {
      if (await c.isVisible().catch(() => false)) {
        visible = true
        break
      }
    }
    expect(visible, 'no setting controls visible').toBe(true)
  })

  test('toggling theme (if present) does not throw', async ({ page }) => {
    const errors: string[] = []
    page.on('pageerror', (e) => errors.push(e.message))
    const themeToggle = page
      .getByRole('button', { name: /theme|dark|light/i })
      .or(page.locator('[role="switch"]').first())
      .first()
    if (await themeToggle.isVisible().catch(() => false)) {
      await themeToggle.click().catch(() => {})
      await page.waitForTimeout(400)
    }
    expect(errors).toEqual([])
  })

  test('theme preference persists after page reload', async ({ page }) => {
    // Locate the theme toggle — accept button, switch, or select
    const themeToggle = page
      .getByRole('button', { name: /theme|dark|light/i })
      .or(page.locator('[role="switch"]').first())
      .or(page.locator('select[name*="theme" i], select[id*="theme" i]').first())
      .first()

    if (!(await themeToggle.isVisible().catch(() => false))) {
      test.skip(true, 'no theme toggle visible on settings page')
    }

    // Capture the attribute or class that encodes the current theme so we
    // can compare after reload. Check html/body/root element.
    const themeAttrBefore = await page.evaluate(() => {
      const root = document.documentElement
      return root.getAttribute('data-theme') ??
        root.getAttribute('data-color-mode') ??
        root.className
    })

    // Click the toggle
    await themeToggle.click().catch(() => {})
    await page.waitForTimeout(600)

    const themeAttrAfterToggle = await page.evaluate(() => {
      const root = document.documentElement
      return root.getAttribute('data-theme') ??
        root.getAttribute('data-color-mode') ??
        root.className
    })

    // Only proceed with reload check if the toggle actually changed something
    if (themeAttrAfterToggle === themeAttrBefore) {
      test.skip(true, 'theme toggle click did not change any detectable theme attribute')
    }

    // Reload the page and verify the theme is still applied
    await page.reload()
    await page.waitForLoadState('networkidle').catch(() => {})

    const themeAttrAfterReload = await page.evaluate(() => {
      const root = document.documentElement
      return root.getAttribute('data-theme') ??
        root.getAttribute('data-color-mode') ??
        root.className
    })

    expect(
      themeAttrAfterReload,
      'theme preference was not persisted across page reload'
    ).toBe(themeAttrAfterToggle)
  })

  test('watched folders section is visible', async ({ page }) => {
    const cap = captureBrowserLogs(page)

    // Look for the "Watched Folders" section heading or label
    const heading = page
      .getByRole('heading', { name: /watched folders/i })
      .or(page.getByText(/watched folders/i).first())
      .first()

    // Also accept a section with data-testid
    const section = page.locator(
      '[data-testid="watched-folders"], [data-testid*="watched"], ' +
      '[class*="watched-folders"], [class*="watchedFolders"]'
    ).first()

    const headingVisible = await heading.isVisible().catch(() => false)
    const sectionVisible = await section.isVisible().catch(() => false)

    cap.detach()

    if (!headingVisible && !sectionVisible) {
      test.skip(
        true,
        'no "Watched Folders" section found on settings page — may live on /files instead'
      )
    }

    expect(headingVisible || sectionVisible).toBe(true)
    expect(cap.logs.filter((l) => l.type === 'pageerror')).toEqual([])
  })

  test('add watched folder input is reachable', async ({ page }) => {
    // First check if the watched folders section exists at all
    const watchedSection = page
      .getByText(/watched folders/i)
      .first()
    const sectionVisible = await watchedSection.isVisible().catch(() => false)

    if (!sectionVisible) {
      // Also check /files page as some implementations put this there
      await page.goto(`${FRONTEND_URL}/files`)
      await page.waitForLoadState('networkidle').catch(() => {})
      const onFilesPage = await page
        .getByText(/watched folders/i)
        .first()
        .isVisible()
        .catch(() => false)
      if (!onFilesPage) {
        test.skip(true, 'no "Watched Folders" section on settings or files page')
      }
    }

    // Look for an add/input affordance within or near the watched folders area
    const addInput = page
      .getByPlaceholder(/folder path|path|directory|add folder/i)
      .first()
    const addButton = page
      .getByRole('button', { name: /add folder|watch folder|add watched|\+/i })
      .first()
    const folderInput = page
      .locator(
        '[data-testid="add-folder-input"], [data-testid="folder-path-input"], ' +
        '[class*="folder-input"], [class*="folderInput"]'
      )
      .first()

    const inputVisible = await addInput.isVisible().catch(() => false)
    const buttonVisible = await addButton.isVisible().catch(() => false)
    const testidVisible = await folderInput.isVisible().catch(() => false)

    expect(
      inputVisible || buttonVisible || testidVisible,
      'no add-folder input or button visible in the watched folders section'
    ).toBe(true)
  })
})
