import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'

import { repositoryRoot as repoRoot } from './server/repository'
const dirs = {
  cv: join(repoRoot, 'cv'),
  packs: join(repoRoot, 'packs'),
  pipeline: join(repoRoot, 'pipeline'),
  scripts: join(repoRoot, 'scripts'),
  mcp: join(repoRoot, 'mcp'),
  dashboard: join(repoRoot, 'dashboard'),
}

const files = {
  variantProfiles: join(dirs.cv, 'variant_profiles.yaml'),
  smoke: join(dirs.scripts, 'smoke_repo.sh'),
  verify: join(dirs.scripts, 'verify_patch.sh'),
  mcpServer: join(dirs.mcp, 'server.py'),
  dashboardPkg: join(dirs.dashboard, 'package.json'),
  actionPlan: join(dirs.pipeline, 'recruiter_action_plan.jsonl'),
  sessionState: join(dirs.pipeline, 'recruiter_session_state.json'),
  applications: join(dirs.pipeline, 'applications.csv'),
  scoutLog: join(dirs.pipeline, 'scout.log'),
  hiringAction: join(dirs.pipeline, 'hiring_network_action_plan.jsonl'),
  hiringState: join(dirs.pipeline, 'hiring_network_run_state.json'),
  mcpDiscovery1: join(dirs.pipeline, 'mcp_discovery_batch.jsonl'),
  mcpDiscovery2: join(dirs.pipeline, 'mcp_discovery_batch2.jsonl'),
}

export type WorkflowCheck = {
  label: string
  command: string
  available: boolean
  detail: string
}

export type Artifact = {
  label: string
  path: string
  exists: boolean
  updatedAt: string | null
  previewLines: string[]
}

export type DashboardOverview = {
  generatedAt: string
  health: {
    mcp: {
      ok: boolean
      message: string
      url: string
    }
  }
  counts: {
    cvVariants: number
    packs: number
    applicationRows: number
    actionPlanRows: number
    sessionRows: number
    mcpDiscoveryRows: number
    mcpDiscoveryRows2: number
    summaryReports: number
  }
  workflowChecks: WorkflowCheck[]
  latestSummary: Artifact
  recentPacks: Artifact[]
  recentPipelineFiles: Artifact[]
  dataSources: { label: string; path: string; exists: boolean }[]
}

function safeRead(path: string): string {
  try {
    return readFileSync(path, 'utf8')
  } catch {
    return ''
  }
}

function safeStat(path: string) {
  if (!existsSync(path)) return null
  try {
    return statSync(path)
  } catch {
    return null
  }
}

function safeDirEntries(path: string): string[] {
  if (!existsSync(path)) return []
  try {
    return readdirSync(path)
  } catch {
    return []
  }
}

function splitLines(text: string): string[] {
  return text.split(/\r?\n/)
}

function countCsvRows(path: string): number {
  const text = safeRead(path)
  const lines = splitLines(text).filter((line) => line.trim())
  return lines.length > 0 ? lines.length - 1 : 0
}

function countJsonlRows(path: string): number {
  return splitLines(safeRead(path)).filter((line) => line.trim()).length
}

function countDirectories(path: string): number {
  return safeDirEntries(path).filter((name) => safeStat(join(path, name))?.isDirectory()).length
}

function countVariantProfiles(path: string): number {
  const text = safeRead(path)
  if (!text.trim()) return 0

  let inVariants = false
  let count = 0
  for (const rawLine of splitLines(text)) {
    const line = rawLine.replace(/#.*$/, '').trimEnd()
    if (!line.trim()) continue

    if (!inVariants) {
      if (line.trim() === 'variants:') {
        inVariants = true
      }
      continue
    }

    if (/^\S/.test(line)) break
    if (/^  [A-Za-z0-9_-]+:\s*$/.test(line)) {
      count += 1
    }
  }
  return count
}

function summarizeTextFile(path: string, previewLines = 12): Artifact {
  const stat = safeStat(path)
  const lines = splitLines(safeRead(path))
    .filter((line) => line.trim())
    .slice(0, previewLines)
  return {
    label: path.split('/').pop() || path,
    path: relative(repoRoot, path) || path,
    exists: !!stat,
    updatedAt: stat ? stat.mtime.toISOString() : null,
    previewLines: lines,
  }
}

function recentArtifacts(path: string, pattern: RegExp, limit = 5, kind: 'any' | 'file' | 'directory' = 'any'): Artifact[] {
  return safeDirEntries(path)
    .filter((name) => pattern.test(name))
    .map((name) => {
      const fullPath = join(path, name)
      const stat = safeStat(fullPath)
      return {
        label: name,
        path: relative(repoRoot, fullPath) || fullPath,
        exists: !!stat,
        updatedAt: stat ? stat.mtime.toISOString() : null,
        previewLines: [],
      }
    })
    .filter((item) => {
      const stat = safeStat(join(repoRoot, item.path))
      if (!stat) return false
      if (kind === 'file') return stat.isFile()
      if (kind === 'directory') return stat.isDirectory()
      return true
    })
    .sort((a, b) => (b.updatedAt || '').localeCompare(a.updatedAt || ''))
    .slice(0, limit)
}

function latestSummaryReport(): Artifact {
  const summaries = recentArtifacts(repoRoot, /^summary_report_.*\.md$/, 1, 'file')
  return summaries[0] ?? summarizeTextFile(join(repoRoot, 'summary_report_latest.md'), 12)
}

async function probeMcpHealth() {
  const url = 'http://127.0.0.1:8000/health'
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 1200)
  try {
    const response = await fetch(url, { cache: 'no-store', signal: controller.signal })
    if (!response.ok) {
      return { ok: false, message: `HTTP ${response.status}`, url }
    }
    const data = await response.json().catch(() => null)
    return {
      ok: Boolean(data?.ok),
      message: data?.service ? `${data.service} healthy` : 'healthy',
      url,
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : 'unavailable'
    return { ok: false, message: `offline or unavailable (${message})`, url }
  } finally {
    clearTimeout(timeout)
  }
}

function parseSessionRows(): number {
  const raw = safeRead(files.sessionState)
  if (!raw.trim()) return 0
  try {
    const parsed = JSON.parse(raw) as { queue?: unknown }
    return Array.isArray(parsed.queue) ? parsed.queue.length : 0
  } catch {
    return 0
  }
}

function workflowChecks(): WorkflowCheck[] {
  return [
    {
      label: 'Smoke harness',
      command: './scripts/smoke_repo.sh',
      available: existsSync(files.smoke),
      detail: existsSync(files.smoke) ? 'available' : 'missing',
    },
    {
      label: 'Patch verification',
      command: './scripts/verify_patch.sh',
      available: existsSync(files.verify),
      detail: existsSync(files.verify) ? 'available' : 'missing',
    },
    {
      label: 'Dashboard app',
      command: 'cd dashboard && npm run build',
      available: existsSync(files.dashboardPkg),
      detail: existsSync(files.dashboardPkg) ? 'Next.js MVP present' : 'missing',
    },
    {
      label: 'MCP server',
      command: 'python mcp/server.py',
      available: existsSync(files.mcpServer),
      detail: existsSync(files.mcpServer) ? 'health + score endpoint' : 'missing',
    },
    {
      label: 'Recruiter preflight',
      command: 'python -m career_job_search.recruiters.orchestrator preflight --browse-status',
      available: existsSync(join(repoRoot, 'src', 'career_job_search', 'recruiters', 'orchestrator.py')),
      detail: 'reads repo state files',
    },
    {
      label: 'Batch matching',
      command: 'python -m career_job_search.opportunities.batch --dry-run',
      available: existsSync(join(repoRoot, 'src', 'career_job_search', 'opportunities', 'batch.py')),
      detail: 'generates packs and summaries',
    },
  ]
}

export async function getDashboardOverview(): Promise<DashboardOverview> {
  const summary = latestSummaryReport()

  const packDirs = recentArtifacts(dirs.packs, /.*/, 5, 'directory')
  const pipelineArtifacts = [
    summarizeTextFile(files.sessionState, 8),
    summarizeTextFile(files.actionPlan, 8),
    summarizeTextFile(files.scoutLog, 8),
    summarizeTextFile(files.hiringState, 8),
    summarizeTextFile(files.hiringAction, 8),
    summarizeTextFile(files.applications, 8),
    summarizeTextFile(files.mcpDiscovery1, 8),
    summarizeTextFile(files.mcpDiscovery2, 8),
  ]
    .filter((item) => item.exists)
    .sort((a, b) => (b.updatedAt || '').localeCompare(a.updatedAt || ''))
    .slice(0, 5)

  return {
    generatedAt: new Date().toISOString(),
    health: {
      mcp: await probeMcpHealth(),
    },
    counts: {
      cvVariants: countVariantProfiles(files.variantProfiles),
      packs: countDirectories(dirs.packs),
      applicationRows: countCsvRows(files.applications),
      actionPlanRows: countJsonlRows(files.actionPlan),
      sessionRows: parseSessionRows(),
      mcpDiscoveryRows: countJsonlRows(files.mcpDiscovery1),
      mcpDiscoveryRows2: countJsonlRows(files.mcpDiscovery2),
      summaryReports: safeDirEntries(repoRoot).filter((name) => /^summary_report_.*\.md$/.test(name)).length,
    },
    workflowChecks: workflowChecks(),
    latestSummary: summary,
    recentPacks: packDirs,
    recentPipelineFiles: pipelineArtifacts,
    dataSources: [
      { label: 'MCP server', path: relative(repoRoot, files.mcpServer), exists: existsSync(files.mcpServer) },
      { label: 'Variant profiles', path: relative(repoRoot, files.variantProfiles), exists: existsSync(files.variantProfiles) },
      { label: 'Smoke harness', path: relative(repoRoot, files.smoke), exists: existsSync(files.smoke) },
      { label: 'Verification script', path: relative(repoRoot, files.verify), exists: existsSync(files.verify) },
      { label: 'Applications CSV', path: relative(repoRoot, files.applications), exists: existsSync(files.applications) },
      { label: 'Session state', path: relative(repoRoot, files.sessionState), exists: existsSync(files.sessionState) },
    ],
  }
}

export { dirs as dashboardDirs, files as dashboardFiles }
