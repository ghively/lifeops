import { chromium } from '@playwright/test';

const BASE = 'http://localhost:5173'
const API = 'http://localhost:8010/api/v1'

async function main() {
  const browser = await chromium.launch()
  const context = await browser.newContext()
  const page = await context.newPage()

  let errors = []
  page.on('console', msg => {
    if (msg.type() === 'error') errors.push(msg.text())
  })
  page.on('pageerror', err => {
    errors.push(err.message)
  })

  // Login
  await page.goto(`${BASE}/login`, { waitUntil: 'networkidle' })
  await page.fill('input[type="email"]', 'e2ewalk@test.com')
  await page.fill('input[type="password"]', 'password123')
  await page.click('button:has-text("Sign in")')
  await page.waitForTimeout(3000)

  // Create object
  const token = await page.evaluate(() => localStorage.getItem('access_token'))
  const res = await fetch(`${API}/objects`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ type: 'page', title: 'React Fix Test', content: '', properties: {} }),
  })
  const obj = await res.json()

  // Navigate to object
  await page.goto(`${BASE}/object/${obj.id}`, { waitUntil: 'networkidle' })
  await page.waitForTimeout(3000)

  // Check for React errors (exclude WS collaboration errors)
  const reactErrors = errors.filter(e => 
    !e.includes('WebSocket') && 
    !e.includes('collaboration') &&
    !e.includes('CollaborationStore')
  )

  const bodyText = await page.innerText('body').catch(() => '')
  const hasContent = bodyText.length > 100

  console.log('=== RESULTS ===')
  console.log('Page has content:', hasContent)
  console.log('React errors:', reactErrors.length)
  if (reactErrors.length > 0) {
    reactErrors.forEach(e => console.log('  ERROR:', e.substring(0, 200)))
  }
  console.log('Title visible:', await page.locator('h1').count() > 0)
  console.log('Editor visible:', await page.locator('[contenteditable]').count() > 0)
  console.log('Toolbar visible:', await page.locator('button:has-text("Type")').count() > 0)

  await page.screenshot({ path: 'e2e/screenshots/react310-fix-verified.png' })
  await browser.close()
}

main().catch(e => console.error(e))
