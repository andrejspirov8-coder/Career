import { spawn } from 'node:child_process'

import { repositoryRoot } from './repository'

const helperScripts = {
  analytics: 'tools/career_analytics.py',
  automation: 'tools/automation_control.py',
  cvCatalogue: 'tools/cv_catalogue.py',
  cvStudio: 'tools/cv_studio.py',
  developmentAgents: 'tools/local_dev_agents.py',
  localDrafting: 'tools/local_drafting.py',
  notifications: 'tools/notification_center.py',
  opportunities: 'tools/opportunity_dashboard.py',
  recruiters: 'tools/recruiter_dashboard.py',
  searchPreferences: 'tools/search_preferences.py',
  workspace: 'tools/workspace_control.py',
} as const

export type PythonHelperName = keyof typeof helperScripts

export type PythonProcessResult = {
  stdout: string
  stderr: string
  exitCode: number
}

import type { PythonHelperEnvelopeV1 as GeneratedPythonHelperEnvelopeV1 } from '@/lib/generated/envelope'

export type PythonHelperEnvelopeV1<T> = GeneratedPythonHelperEnvelopeV1 & {
  data?: T
}

export type PythonHelperOptions = {
  timeoutMs?: number
  maxOutputBytes?: number
  input?: unknown
  inputText?: string
  errorLabel?: string
}

const defaultTimeoutMs = 30_000
const defaultMaxOutputBytes = 8 * 1024 * 1024

function safeExcerpt(value: string): string {
  const cleaned = value.trim().replace(/\s+/g, ' ')
  return cleaned.length > 1_500 ? `${cleaned.slice(0, 1_497)}...` : cleaned
}

function validateArguments(args: readonly string[]): void {
  if (args.length > 100 || args.some((value) => typeof value !== 'string' || value.includes('\0') || value.length > 10_000)) {
    throw new Error('Python helper arguments are invalid.')
  }
}

export function parsePythonHelperEnvelope<T>(
  result: PythonProcessResult,
  errorLabel = 'Python helper',
): T {
  let payload: PythonHelperEnvelopeV1<T> | null = null
  try {
    payload = JSON.parse(result.stdout || '{}') as PythonHelperEnvelopeV1<T>
  } catch {
    if (result.exitCode === 0) throw new Error(`${errorLabel} returned invalid JSON.`)
  }
  if (payload && payload.schema !== 'career_python_helper_v1') {
    throw new Error(`${errorLabel} returned an unsupported response version.`)
  }
  if (result.exitCode === 0 && payload?.ok && payload.data !== undefined) return payload.data

  const details = [
    payload?.error ? safeExcerpt(payload.error) : '',
    result.stderr ? `stderr: ${safeExcerpt(result.stderr)}` : '',
    !payload && result.stdout ? `stdout: ${safeExcerpt(result.stdout)}` : '',
  ].filter(Boolean)
  throw new Error(details.join(' | ') || `${errorLabel} failed with exit code ${result.exitCode}.`)
}

export function executePythonHelper(
  helper: PythonHelperName,
  args: readonly string[] = [],
  options: PythonHelperOptions = {},
): Promise<PythonProcessResult> {
  validateArguments(args)
  if (options.input !== undefined && options.inputText !== undefined) {
    throw new Error('Python helper input must use either JSON or text, not both.')
  }
  const timeoutMs = options.timeoutMs ?? defaultTimeoutMs
  const maxOutputBytes = options.maxOutputBytes ?? defaultMaxOutputBytes
  const errorLabel = options.errorLabel || 'Python helper'

  return new Promise((resolvePromise, reject) => {
    const child = spawn('uv', ['run', 'python', helperScripts[helper], ...args], {
      cwd: repositoryRoot,
      env: process.env,
      shell: false,
      stdio: ['pipe', 'pipe', 'pipe'],
      windowsHide: true,
    })
    let stdout = ''
    let stderr = ''
    let settled = false
    let outputTooLarge = false
    const finish = (callback: () => void) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      callback()
    }
    const timer = setTimeout(() => {
      child.kill('SIGTERM')
      finish(() => reject(new Error(`${errorLabel} timed out after ${Math.ceil(timeoutMs / 1_000)} seconds.`)))
    }, timeoutMs)

    child.stdout.setEncoding('utf8')
    child.stderr.setEncoding('utf8')
    child.stdout.on('data', (chunk: string) => {
      stdout += chunk
      if (stdout.length > maxOutputBytes) {
        outputTooLarge = true
        child.kill('SIGTERM')
      }
    })
    child.stderr.on('data', (chunk: string) => {
      stderr += chunk
      if (stderr.length > maxOutputBytes) {
        outputTooLarge = true
        child.kill('SIGTERM')
      }
    })
    child.on('error', (error) => finish(() => reject(new Error(`${errorLabel} could not start: ${error.message}`))))
    child.on('close', (exitCode) => finish(() => {
      if (outputTooLarge) {
        reject(new Error(`${errorLabel} returned too much data.`))
        return
      }
      resolvePromise({ stdout, stderr, exitCode: exitCode ?? 1 })
    }))
    child.stdin.end(
      options.inputText ?? (options.input === undefined ? '' : JSON.stringify(options.input)),
    )
  })
}

export async function runPythonHelper<T>(
  helper: PythonHelperName,
  args: readonly string[] = [],
  options: PythonHelperOptions = {},
): Promise<T> {
  const result = await executePythonHelper(helper, args, options)
  return parsePythonHelperEnvelope<T>(result, options.errorLabel)
}
