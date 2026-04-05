const { chromium } = require('/opt/homebrew/lib/node_modules/playwright');

const BASE = 'http://localhost:3010';
const results = [];

function log(cat, name, passed, detail) {
  results.push({cat, name, passed, detail});
  const icon = passed ? '✅' : '❌';
  let msg = `  ${icon} ${cat}: ${name}`;
  if (detail) msg += ` (${detail})`;
  console.log(msg);
}

(async () => {
  const browser = await chromium.launch({headless: true});
  const ctx = await browser.newContext({viewport: {width: 1280, height: 800}});
  const page = await ctx.newPage();

  const consoleErrors = [];
  const networkErrors = [];
  page.on('console', msg => { if (msg.type() === 'error') consoleErrors.push(msg.text()); });
  page.on('requestfailed', req => networkErrors.push(`${req.method()} ${req.url()}`));

  console.log('='.repeat(60));
  console.log('Knowledge OS E2E Walkthrough');
  console.log('='.repeat(60));

  // ==========================================
  // 1. LOGIN PAGE
  // ==========================================
  console.log('\n[1] Login Page');
  const resp = await page.goto(BASE, {waitUntil: 'networkidle', timeout: 15000});
  log('Landing', 'Page loads', resp.status() === 200);
  log('Landing', 'Title', (await page.title()) === 'Knowledge OS');
  log('Login', 'Email input (#login-email)', await page.locator('#login-email').count() > 0);
  log('Login', 'Password input (#login-password)', await page.locator('#login-password').count() > 0);
  log('Login', 'Sign in button', await page.locator('button:has-text("Sign in")').count() > 0);
  log('Login', 'Sign up button', await page.locator('button:has-text("Sign up")').count() > 0);
  log('Login', 'Forgot password', await page.locator('a:has-text("Forgot password")').count() > 0);

  // ==========================================
  // 2. REGISTER
  // ==========================================
  console.log('\n[2] Registration');
  await page.locator('button:has-text("Sign up")').click();
  await page.waitForTimeout(1000);
  log('Register', 'Register form visible', await page.locator('#register-email').count() > 0);

  await page.locator('#register-email').fill('e2ewalk@test.com');
  await page.locator('#register-username').fill('e2ewalk');
  await page.locator('#register-password').fill('WalkPass123!');
  await page.locator('#register-confirm-password').fill('WalkPass123!');

  await page.locator('button[type="submit"]').click();
  await page.waitForTimeout(3000);

  const registered = page.url() === BASE || page.url() === BASE + '/';
  log('Register', 'Success', registered, `url=${page.url()}`);

  if (!registered) {
    const errs = await page.evaluate(() => {
      return [...document.querySelectorAll('[class*="destructive"], [role="alert"]')].map(e => e.textContent?.trim()).filter(Boolean);
    });
    if (errs.length) log('Register', 'Error', false, errs[0]?.slice(0,100));
  }

  // ==========================================
  // 3. LOGGED-IN PAGES
  // ==========================================
  const isApp = registered || !page.url().includes('/login');

  if (!isApp) {
    // Try login
    console.log('\n[3] Login (fallback)');
    if (await page.locator('button:has-text("Sign in")').count() > 0) {
      await page.locator('button:has-text("Sign in")').click();
      await page.waitForTimeout(500);
    }
    await page.locator('#login-email').fill('e2ewalk@test.com');
    await page.locator('#login-password').fill('WalkPass123!');
    await page.locator('button[type="submit"]').click();
    await page.waitForTimeout(3000);
  }

  const loggedIn = !page.url().includes('/login') && !page.url().includes('/register');
  log('App', 'Logged in', loggedIn, `url=${page.url()}`);

  if (loggedIn) {
    // ==========================================
    // 4. OUTLINER
    // ==========================================
    console.log('\n[4] Outliner');
    const outlinerText = await page.evaluate(() => document.body.innerText);
    log('Outliner', 'Page renders', outlinerText.length > 100, `${outlinerText.length} chars`);

    const hasSidebar = await page.locator('nav, aside, [class*="sidebar"]').count() > 0;
    log('Outliner', 'Sidebar present', hasSidebar);

    const hasNewBtn = await page.locator('button:has-text("New"), button:has-text("Create"), button:has-text("+")').count() > 0;
    log('Outliner', 'New/Create button', hasNewBtn);

    if (hasNewBtn) {
      await page.locator('button:has-text("New"), button:has-text("Create"), button:has-text("+")').nth(0).click();
      await page.waitForTimeout(1000);

      const typeOpt = page.locator('text=Note, text=Page, text=Task');
      if (await typeOpt.count() > 0) {
        await typeOpt.nth(0).click();
        await page.waitForTimeout(500);

        const titleInput = page.locator('input[placeholder*="title"], input[name="title"]');
        if (await titleInput.count() > 0) {
          await titleInput.first.fill('E2E Walkthrough Note');

          const submitBtn = page.locator('button:has-text("Create"), button:has-text("Save"), button[type="submit"]');
          if (await submitBtn.count() > 0) {
            await submitBtn.last.click();
            await page.waitForTimeout(2000);
            log('Outliner', 'Created object', true);
          }
        }
      }
    }

    // ==========================================
    // 5. SEARCH
    // ==========================================
    console.log('\n[5] Search');
    await page.goto(`${BASE}/search`, {waitUntil: 'networkidle', timeout: 10000});
    await page.waitForTimeout(1000);
    log('Search', 'Page loads', !page.url().includes('login'));

    const searchInput = page.locator('input[type="search"], input[placeholder*="search"], input[name="q"]');
    if (await searchInput.count() > 0) {
      await searchInput.first.fill('walkthrough');
      await page.waitForTimeout(2000);
      log('Search', 'Search executed', true);
    } else {
      log('Search', 'Search input', false, 'not found');
    }

    // ==========================================
    // 6. TASKS
    // ==========================================
    console.log('\n[6] Tasks');
    await page.goto(`${BASE}/tasks`, {waitUntil: 'networkidle', timeout: 10000});
    await page.waitForTimeout(1000);
    log('Tasks', 'Page loads', !page.url().includes('login'));
    if (!page.url().includes('login')) {
      const text = await page.evaluate(() => document.body.innerText);
      log('Tasks', 'Has task UI', ['task', 'priority', 'status'].some(kw => text.toLowerCase().includes(kw)));
    }

    // ==========================================
    // 7. AGENTS
    // ==========================================
    console.log('\n[7] Agents');
    await page.goto(`${BASE}/agents`, {waitUntil: 'networkidle', timeout: 10000});
    await page.waitForTimeout(1000);
    log('Agents', 'Page loads', !page.url().includes('login'));
    if (!page.url().includes('login')) {
      const text = await page.evaluate(() => document.body.innerText);
      log('Agents', 'Has agent UI', ['agent', 'chat', 'status'].some(kw => text.toLowerCase().includes(kw)));
    }

    // ==========================================
    // 8. FILES
    // ==========================================
    console.log('\n[8] Files');
    await page.goto(`${BASE}/files`, {waitUntil: 'networkidle', timeout: 10000});
    await page.waitForTimeout(1000);
    log('Files', 'Page loads', !page.url().includes('login'));
    if (!page.url().includes('login')) {
      const text = await page.evaluate(() => document.body.innerText);
      log('Files', 'Has file UI', ['file', 'folder', 'watch'].some(kw => text.toLowerCase().includes(kw)));
    }

    // ==========================================
    // 9. SETTINGS
    // ==========================================
    console.log('\n[9] Settings');
    await page.goto(`${BASE}/settings`, {waitUntil: 'networkidle', timeout: 10000});
    await page.waitForTimeout(1000);
    log('Settings', 'Page loads', !page.url().includes('login'));
    if (!page.url().includes('login')) {
      const text = await page.evaluate(() => document.body.innerText);
      log('Settings', 'Has settings UI', ['setting', 'backup', 'openclaw'].some(kw => text.toLowerCase().includes(kw)));
    }

    // ==========================================
    // 10. NAVIGATION
    // ==========================================
    console.log('\n[10] Navigation');
    await page.goto(BASE, {waitUntil: 'networkidle', timeout: 10000});
    const navLinks = page.locator('nav a, aside a, [class*="sidebar"] a');
    log('Navigation', `Nav links (${await navLinks.count()})`, await navLinks.count() >= 3);
    await page.screenshot({path: 'e2e-screenshot-final.png', fullPage: true});
    log('Navigation', 'Screenshot', true, 'e2e-screenshot-final.png');
  } else {
    console.log('\n[4-10] Skipped — could not log in');
    log('App', 'All pages skipped', false, 'login failed');
  }

  // ==========================================
  // SUMMARY
  // ==========================================
  console.log('\n' + '='.repeat(60));
  const passed = results.filter(r => r.passed).length;
  const failed = results.filter(r => !r.passed).length;
  console.log(`Results: ${passed}/${results.length} passed, ${failed} failed`);
  console.log('='.repeat(60));

  if (failed > 0) {
    console.log('\nFailures:');
    results.filter(r => !r.passed).forEach(r => console.log(`  ❌ ${r.cat}: ${r.name} — ${r.detail || ''}`));
  }

  if (consoleErrors.length > 0) {
    console.log(`\n⚠️  Console errors (${consoleErrors.length}):`);
    consoleErrors.slice(0, 5).forEach(e => console.log(`  ${e.slice(0, 150)}`));
  }

  if (networkErrors.length > 0) {
    console.log(`\n⚠️  Network errors (${networkErrors.length}):`);
    networkErrors.slice(0, 5).forEach(e => console.log(`  ${e.slice(0, 150)}`));
  }

  await browser.close();
  process.exit(failed > 0 ? 1 : 0);
})();
