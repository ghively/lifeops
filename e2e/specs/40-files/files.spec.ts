import { test, expect } from '@playwright/test'
import { captureBrowserLogs } from '../../helpers/console'
import { FRONTEND_URL } from '../../helpers/env'
import { writeFileSync, mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

test.describe('Files page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/files`)
    await page.waitForLoadState('networkidle').catch(() => {})
  })

  test('renders without throwing', async ({ page }) => {
    const cap = captureBrowserLogs(page)
    await page.waitForTimeout(500)
    cap.detach()
    expect(cap.logs.filter((l) => l.type === 'pageerror')).toEqual([])
  })

  test('upload affordance is present', async ({ page }) => {
    const fileInput = page.locator('input[type="file"]').first()
    const uploadButton = page
      .getByRole('button', { name: /upload|add file|choose file/i })
      .first()
    const visible =
      (await fileInput.count()) > 0 ||
      (await uploadButton.isVisible().catch(() => false))
    expect(visible, 'no upload affordance on /files').toBe(true)
  })

  test('upload a small text file (best-effort)', async ({ page }) => {
    const fileInput = page.locator('input[type="file"]').first()
    if ((await fileInput.count()) === 0) {
      test.skip(true, 'no <input type=file> exposed')
    }

    const dir = mkdtempSync(join(tmpdir(), 'kos-e2e-'))
    const filePath = join(dir, `e2e-${Date.now()}.txt`)
    writeFileSync(filePath, 'hello from the e2e suite')

    await fileInput.setInputFiles(filePath)
    await page.waitForTimeout(2500)
    // We don't assert a specific success toast — implementations vary.
    // Just check no fatal error happened.
    const err = await page
      .locator('text=/upload failed|error|exception/i')
      .first()
      .isVisible()
      .catch(() => false)
    expect(err).toBeFalsy()
  })
})
