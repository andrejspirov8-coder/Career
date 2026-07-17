import { basename, resolve } from 'node:path'

const rootEnvironmentVariable = 'CAREER_JOB_SEARCH_ROOT'

export function resolveRepositoryRoot(
  cwd = process.cwd(),
  configuredRoot = process.env[rootEnvironmentVariable],
): string {
  const configured = configuredRoot?.trim()
  if (configured) return resolve(configured)
  return resolve(cwd, basename(resolve(cwd)) === 'dashboard' ? '..' : '.')
}

export const repositoryRoot = resolveRepositoryRoot()
