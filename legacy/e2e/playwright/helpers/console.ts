import type { Page } from '@playwright/test'

export type CapturedLog = {
  type: 'console' | 'pageerror' | 'requestfailed'
  level?: string
  text: string
  url?: string
  location?: string
}

/**
 * Attach listeners that capture browser-side problems (console errors, uncaught
 * exceptions, network failures). Returns a getter for the accumulated logs and
 * a teardown function. Tests don't need to fail just because something logged
 * — but the report should surface the noise.
 */
export function captureBrowserLogs(page: Page) {
  const logs: CapturedLog[] = []

  const onConsole = (msg: import('@playwright/test').ConsoleMessage) => {
    const level = msg.type()
    if (level === 'error' || level === 'warning') {
      logs.push({
        type: 'console',
        level,
        text: msg.text(),
        location: `${msg.location().url}:${msg.location().lineNumber}`,
      })
    }
  }
  const onPageError = (err: Error) => {
    logs.push({ type: 'pageerror', text: `${err.name}: ${err.message}` })
  }
  const onRequestFailed = (req: import('@playwright/test').Request) => {
    const failure = req.failure()
    if (!failure) return
    // Ignore expected aborts on navigation.
    if (/aborted|interrupted/i.test(failure.errorText)) return
    logs.push({
      type: 'requestfailed',
      text: failure.errorText,
      url: req.url(),
    })
  }

  page.on('console', onConsole)
  page.on('pageerror', onPageError)
  page.on('requestfailed', onRequestFailed)

  return {
    logs,
    detach: () => {
      page.off('console', onConsole)
      page.off('pageerror', onPageError)
      page.off('requestfailed', onRequestFailed)
    },
  }
}
