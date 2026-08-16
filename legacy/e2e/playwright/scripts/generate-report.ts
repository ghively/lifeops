/**
 * Reads the Playwright JSON output and writes a human-readable Markdown
 * report to e2e/REPORT.md. The report is the canonical "what is broken"
 * artifact — Claude (the assistant) is instructed to read it via CLAUDE.md
 * whenever the user asks about e2e results.
 */
import { readFileSync, writeFileSync, existsSync } from 'node:fs'
import { resolve, relative } from 'node:path'

type PWError = { message?: string; stack?: string; value?: string }
type PWAttachment = { name: string; path?: string; contentType?: string }
type PWResult = {
  status: 'passed' | 'failed' | 'timedOut' | 'skipped' | 'interrupted'
  duration: number
  errors?: PWError[]
  attachments?: PWAttachment[]
  stdout?: { text?: string }[]
  stderr?: { text?: string }[]
}
type PWTest = {
  title: string
  results: PWResult[]
  expectedStatus?: string
  projectName?: string
  location?: { file?: string; line?: number }
}
type PWSpec = {
  title: string
  file: string
  tests: PWTest[]
}
type PWSuite = { title: string; specs?: PWSpec[]; suites?: PWSuite[] }
type PWReport = {
  config?: { rootDir?: string }
  stats?: {
    startTime?: string
    duration?: number
    expected?: number
    skipped?: number
    unexpected?: number
    flaky?: number
  }
  suites: PWSuite[]
}

const ROOT = resolve(__dirname, '..')
const RESULTS_PATH = resolve(ROOT, 'playwright-report/results.json')
const REPORT_PATH = resolve(ROOT, 'REPORT.md')

function flattenSpecs(suite: PWSuite, acc: PWSpec[] = []): PWSpec[] {
  if (suite.specs) acc.push(...suite.specs)
  if (suite.suites) for (const s of suite.suites) flattenSpecs(s, acc)
  return acc
}

function statusEmoji(s: PWResult['status']) {
  switch (s) {
    case 'passed':
      return '✅'
    case 'failed':
    case 'timedOut':
      return '❌'
    case 'skipped':
      return '⏭️'
    case 'interrupted':
      return '⚠️'
    default:
      return '❓'
  }
}

function shortenError(e: PWError, max = 600): string {
  const text = e.message || e.value || e.stack || 'unknown'
  if (text.length <= max) return text.trim()
  return text.slice(0, max).trim() + ' …(truncated)'
}

function relAttachment(p?: string): string | null {
  if (!p) return null
  try {
    return relative(ROOT, p)
  } catch {
    return p
  }
}

function buildReport(report: PWReport, exitCode: number): string {
  const lines: string[] = []
  const stats = report.stats || {}
  const startedAt = stats.startTime || new Date().toISOString()
  const durationMs = stats.duration || 0
  const expected = stats.expected || 0
  const skipped = stats.skipped || 0
  const unexpected = stats.unexpected || 0
  const flaky = stats.flaky || 0
  const total = expected + skipped + unexpected + flaky

  lines.push('# Knowledge OS — End-to-End Suite Report')
  lines.push('')
  lines.push(
    'This file is **regenerated on every run** of `e2e/scripts/run-suite.sh`.',
  )
  lines.push(
    'It is the canonical source of "what is broken in the running system" — ',
  )
  lines.push(
    'when the user asks about e2e failures, what to fix, or what to look at,',
  )
  lines.push('this is the file to read.')
  lines.push('')
  lines.push(`- **Started:** ${startedAt}`)
  lines.push(`- **Duration:** ${(durationMs / 1000).toFixed(1)}s`)
  lines.push(
    `- **Total:** ${total} | **Passed:** ${expected} | **Failed:** ${unexpected} | **Flaky:** ${flaky} | **Skipped:** ${skipped}`,
  )
  lines.push(`- **Playwright exit code:** ${exitCode}`)
  lines.push('')

  const allSpecs: PWSpec[] = []
  for (const s of report.suites) flattenSpecs(s, allSpecs)

  // Aggregate failures.
  type Fail = {
    spec: string
    test: string
    file: string
    location?: string
    error: string
    attachments: { name: string; path: string }[]
    project?: string
  }
  const failures: Fail[] = []
  const skipsByReason = new Map<string, string[]>()

  for (const spec of allSpecs) {
    for (const t of spec.tests) {
      const last = t.results[t.results.length - 1]
      if (!last) continue
      if (last.status === 'failed' || last.status === 'timedOut') {
        const errMsg =
          (last.errors || []).map((e) => shortenError(e)).join('\n---\n') ||
          'no error captured'
        const atts = (last.attachments || [])
          .filter(
            (a) =>
              a.path &&
              (a.contentType?.startsWith('image/') ||
                a.contentType?.startsWith('video/') ||
                a.name === 'trace'),
          )
          .map((a) => ({ name: a.name, path: relAttachment(a.path) || '' }))
        failures.push({
          spec: spec.title,
          test: t.title,
          file: spec.file,
          location: t.location
            ? `${t.location.file || spec.file}:${t.location.line || '?'}`
            : spec.file,
          error: errMsg,
          attachments: atts,
          project: t.projectName,
        })
      } else if (last.status === 'skipped') {
        const why =
          (last.errors || []).map((e) => shortenError(e, 120)).join(' / ') ||
          'no reason given'
        if (!skipsByReason.has(why)) skipsByReason.set(why, [])
        skipsByReason.get(why)!.push(`${spec.title} → ${t.title}`)
      }
    }
  }

  // Top section — punch list.
  lines.push('## What Needs to Be Fixed')
  lines.push('')
  if (failures.length === 0) {
    lines.push('🎉 No failing tests. No punch list this run.')
  } else {
    lines.push(
      `${failures.length} failing test${failures.length === 1 ? '' : 's'}. ` +
        'Each entry below should be triaged to a code or infrastructure fix.',
    )
    lines.push('')
    failures.forEach((f, i) => {
      lines.push(`### ${i + 1}. ${f.spec} — ${f.test}`)
      lines.push('')
      lines.push(`- **File:** \`${f.location || f.file}\``)
      if (f.project) lines.push(`- **Project:** ${f.project}`)
      lines.push('')
      lines.push('```')
      lines.push(f.error)
      lines.push('```')
      if (f.attachments.length) {
        lines.push('')
        lines.push('Artifacts:')
        for (const a of f.attachments) {
          lines.push(`- ${a.name}: \`${a.path}\``)
        }
      }
      lines.push('')
    })
  }

  // Per-spec breakdown.
  lines.push('## Per-Spec Breakdown')
  lines.push('')
  lines.push('| Spec | Pass | Fail | Skip | File |')
  lines.push('|---|---:|---:|---:|---|')
  const bySpec = new Map<string, { p: number; f: number; s: number; file: string }>()
  for (const spec of allSpecs) {
    const key = spec.title
    const agg = bySpec.get(key) || { p: 0, f: 0, s: 0, file: spec.file }
    for (const t of spec.tests) {
      const last = t.results[t.results.length - 1]
      if (!last) continue
      if (last.status === 'passed') agg.p++
      else if (last.status === 'skipped') agg.s++
      else agg.f++
    }
    bySpec.set(key, agg)
  }
  for (const [name, agg] of bySpec) {
    lines.push(
      `| ${name} | ${agg.p} | ${agg.f} | ${agg.s} | \`${agg.file}\` |`,
    )
  }
  lines.push('')

  // Skips section — what wasn't exercised.
  if (skipsByReason.size > 0) {
    lines.push('## Skipped (feature not present or precondition not met)')
    lines.push('')
    for (const [reason, tests] of skipsByReason) {
      lines.push(`- **${reason}**`)
      for (const t of tests) lines.push(`  - ${t}`)
    }
    lines.push('')
  }

  lines.push('---')
  lines.push('')
  lines.push(
    `_Regenerate with \`cd e2e && bash scripts/run-suite.sh\`. ` +
      `Last run: ${new Date().toISOString()}._`,
  )
  return lines.join('\n')
}

function main() {
  const exitCode = parseInt(process.env.E2E_EXIT_CODE || '0', 10)

  if (!existsSync(RESULTS_PATH)) {
    const stub = [
      '# Knowledge OS — End-to-End Suite Report',
      '',
      '⚠️ **No results file found.** The Playwright run did not produce',
      `\`${relative(ROOT, RESULTS_PATH)}\`. The most likely cause is that the`,
      'frontend or backend was not reachable when the suite started.',
      '',
      `- Frontend: \`${process.env.E2E_FRONTEND_URL || 'http://localhost:5173'}\``,
      `- Backend:  \`${process.env.E2E_BACKEND_URL || 'http://localhost:8000'}\``,
      '',
      'Bring both up and re-run `bash e2e/scripts/run-suite.sh`.',
      '',
    ].join('\n')
    writeFileSync(REPORT_PATH, stub)
    return
  }

  const raw = readFileSync(RESULTS_PATH, 'utf8')
  const data = JSON.parse(raw) as PWReport
  const md = buildReport(data, exitCode)
  writeFileSync(REPORT_PATH, md)
  console.log(`[report] wrote ${REPORT_PATH}`)
}

main()
