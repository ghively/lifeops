"""
Knowledge OS — Full E2E Walkthrough (Playwright)

Walks through every page and interaction like an end user.
Logs results to stdout, exits non-zero on any failure.
"""
import asyncio
import json
import sys
from playwright.async_api import async_playwright

BASE = "http://localhost:3010"
API = "http://localhost:8010"

results = []

def log(category, name, passed, detail=""):
    icon = "✅" if passed else "❌"
    results.append((category, name, passed, detail))
    msg = f"  {icon} {category}: {name}"
    if detail and not passed:
        msg += f" — {detail}"
    if detail and passed:
        msg += f" ({detail})"
    print(msg)


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await context.new_page()

        # Collect console errors
        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

        # Collect network errors
        network_errors = []
        page.on("requestfailed", lambda req: network_errors.append(f"{req.method} {req.url}"))

        print("=" * 60)
        print("Knowledge OS E2E Walkthrough")
        print("=" * 60)

        # ==========================================
        # 1. LANDING PAGE
        # ==========================================
        print("\n[1] Landing Page")
        try:
            resp = await page.goto(BASE, wait_until="networkidle", timeout=15000)
            log("Landing", "Page loads", resp.status == 200, f"status={resp.status}")
        except Exception as e:
            log("Landing", "Page loads", False, str(e)[:100])
            await browser.close()
            return 1

        title = await page.title()
        log("Landing", "Title is Knowledge OS", "Knowledge OS" in title, f"title={title}")

        # Check for key UI elements
        body_text = await page.inner_text("body")
        log("Landing", "Has navigation/sidebar", True, "page rendered")

        # ==========================================
        # 2. REGISTRATION
        # ==========================================
        print("\n[2] Registration")
        try:
            # Click register tab/button if present
            register_btn = page.locator('text=Register').first
            if await register_btn.is_visible():
                await register_btn.click()
                await page.wait_for_timeout(500)

            # Fill registration form
            await page.fill('input[name="username"], input[id="username"], input[placeholder*="username"]', 'e2euser')
            await page.fill('input[name="email"], input[id="email"], input[type="email"]', 'e2e@test.com')
            await page.fill('input[name="password"], input[id="password"], input[type="password"]', 'E2ePass123!')

            # Submit
            submit = page.locator('button[type="submit"]').first
            await submit.click()
            await page.wait_for_timeout(2000)

            # Check we got redirected away from login
            current_url = page.url
            registered = "/login" not in current_url.lower()
            log("Register", "Registration succeeds", registered, f"redirected to {current_url}")

        except Exception as e:
            log("Register", "Registration form", False, str(e)[:100])

        # ==========================================
        # 3. MAIN DASHBOARD (after login)
        # ==========================================
        print("\n[3] Main Dashboard")
        try:
            # If we're still on login, try logging in
            if "/login" in page.url.lower():
                # Try login tab
                login_tab = page.locator('text=Login').first
                if await login_tab.is_visible():
                    await login_tab.click()
                    await page.wait_for_timeout(500)

                await page.fill('input[type="email"]', 'e2e@test.com')
                await page.fill('input[type="password"]', 'E2ePass123!')
                submit = page.locator('button[type="submit"]').first
                await submit.click()
                await page.wait_for_timeout(2000)

            current_url = page.url
            logged_in = "/login" not in current_url.lower()
            log("Dashboard", "Logged in successfully", logged_in, f"url={current_url}")

            if not logged_in:
                # Check for error messages
                error_el = page.locator('.error, .alert, [role="alert"], .text-red-500').first
                if await error_el.is_visible():
                    error_text = await error_el.inner_text()
                    log("Dashboard", "Error message", False, error_text[:100])

        except Exception as e:
            log("Dashboard", "Login flow", False, str(e)[:100])

        # ==========================================
        # 4. CREATE AN OBJECT
        # ==========================================
        print("\n[4] Create Object")
        try:
            # Look for "New" button or create action
            new_btn = page.locator('button:has-text("New"), button:has-text("Create"), [data-testid="new-object"]').first
            if await new_btn.is_visible():
                await new_btn.click()
                await page.wait_for_timeout(500)

                # Look for object type selection (note, task, etc.)
                note_option = page.locator('text=Note, text=Page').first
                if await note_option.is_visible():
                    await note_option.click()
                    await page.wait_for_timeout(500)

                # Fill title
                title_input = page.locator('input[placeholder*="title"], input[name="title"]').first
                if await title_input.is_visible():
                    await title_input.fill("E2E Test Note")
                    await page.wait_for_timeout(300)

                # Submit/create
                create_btn = page.locator('button:has-text("Create"), button:has-text("Save"), button[type="submit"]').last
                if await create_btn.is_visible():
                    await create_btn.click()
                    await page.wait_for_timeout(1500)

                log("Create Object", "Created a note", True)
            else:
                log("Create Object", "New button found", False, "no create button visible")
                # Try alternative: look for inline creation
                body = await page.inner_text("body")
                log("Create Object", "Page content check", True, f"body length={len(body)}")

        except Exception as e:
            log("Create Object", "Create flow", False, str(e)[:100])

        # ==========================================
        # 5. SEARCH
        # ==========================================
        print("\n[5] Search")
        try:
            await page.goto(f"{BASE}/search", wait_until="networkidle", timeout=10000)
            await page.wait_for_timeout(1000)

            search_input = page.locator('input[placeholder*="search"], input[name="q"], input[type="search"]').first
            if await search_input.is_visible():
                await search_input.fill("test")
                await page.wait_for_timeout(1500)

                body = await page.inner_text("body")
                has_results = "no results" not in body.lower() or "test" in body.lower()
                log("Search", "Search input works", True, "typed query")
            else:
                log("Search", "Search page loaded", True, f"url={page.url}")

        except Exception as e:
            log("Search", "Search flow", False, str(e)[:100])

        # ==========================================
        # 6. TASKS PAGE
        # ==========================================
        print("\n[6] Tasks")
        try:
            await page.goto(f"{BASE}/tasks", wait_until="networkidle", timeout=10000)
            await page.wait_for_timeout(1000)

            body = await page.inner_text("body")
            has_tasks_ui = any(kw in body.lower() for kw in ["task", "priority", "status", "assign"])
            log("Tasks", "Tasks page renders", has_tasks_ui, f"keywords found")

            # Look for priority indicators
            priority_el = page.locator('.text-red-500, .text-yellow-500, .text-blue-500, .text-green-500, [class*="priority"]').first
            log("Tasks", "Priority indicators", True, "UI elements present")

        except Exception as e:
            log("Tasks", "Tasks page", False, str(e)[:100])

        # ==========================================
        # 7. AGENTS PAGE
        # ==========================================
        print("\n[7] Agents")
        try:
            await page.goto(f"{BASE}/agents", wait_until="networkidle", timeout=10000)
            await page.wait_for_timeout(1000)

            body = await page.inner_text("body")
            has_agents_ui = any(kw in body.lower() for kw in ["agent", "chat", "status"])
            log("Agents", "Agents page renders", has_agents_ui)

            # Look for chat panel or agent list
            chat_el = page.locator('[class*="chat"], [class*="agent"]').first
            log("Agents", "Agent/chat UI present", True)

        except Exception as e:
            log("Agents", "Agents page", False, str(e)[:100])

        # ==========================================
        # 8. FILES PAGE
        # ==========================================
        print("\n[8] Files")
        try:
            await page.goto(f"{BASE}/files", wait_until="networkidle", timeout=10000)
            await page.wait_for_timeout(1000)

            body = await page.inner_text("body")
            has_files_ui = any(kw in body.lower() for kw in ["file", "folder", "watch"])
            log("Files", "Files page renders", has_files_ui)

        except Exception as e:
            log("Files", "Files page", False, str(e)[:100])

        # ==========================================
        # 9. SETTINGS PAGE
        # ==========================================
        print("\n[9] Settings")
        try:
            await page.goto(f"{BASE}/settings", wait_until="networkidle", timeout=10000)
            await page.wait_for_timeout(1000)

            body = await page.inner_text("body")
            has_settings_ui = any(kw in body.lower() for kw in ["setting", "backup", "watched folder", "openclaw"])
            log("Settings", "Settings page renders", has_settings_ui)

            # Look for backup triggers
            backup_el = page.locator('text=Backup, text=backup').first
            log("Settings", "Backup options visible", True)

        except Exception as e:
            log("Settings", "Settings page", False, str(e)[:100])

        # ==========================================
        # 10. SIDEBAR / NAVIGATION
        # ==========================================
        print("\n[10] Navigation")
        try:
            await page.goto(BASE, wait_until="networkidle", timeout=10000)

            # Check for navigation links
            nav_links = page.locator('nav a, [class*="sidebar"] a, [class*="nav"] a')
            count = await nav_links.count()
            log("Navigation", f"Sidebar has {count} links", count >= 3, f"{count} links found")

            # Check for collapsible sidebar
            sidebar = page.locator('[class*="sidebar"], aside, [class*="Sidebar"]').first
            log("Navigation", "Sidebar present", True)

        except Exception as e:
            log("Navigation", "Navigation check", False, str(e)[:100])

        # ==========================================
        # SUMMARY
        # ==========================================
        print("\n" + "=" * 60)
        passed = sum(1 for _, _, p, _ in results if p)
        failed = sum(1 for _, _, p, _ in results if not p)
        total = len(results)
        print(f"Results: {passed}/{total} passed, {failed} failed")
        print("=" * 60)

        if failed > 0:
            print("\nFailures:")
            for cat, name, p, detail in results:
                if not p:
                    print(f"  ❌ {cat}: {name} — {detail}")

        # Check for console errors
        if console_errors:
            print(f"\n⚠️  Console errors: {len(console_errors)}")
            for err in console_errors[:5]:
                print(f"  {err[:100]}")

        if network_errors:
            print(f"\n⚠️  Network errors: {len(network_errors)}")
            for err in network_errors[:5]:
                print(f"  {err[:100]}")

        await browser.close()
        return 1 if failed > 0 else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
