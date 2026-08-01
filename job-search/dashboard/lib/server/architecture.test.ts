import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

const dashboardRoot = resolve(process.cwd())
const apiRoot = join(dashboardRoot, 'app', '(dashboard)', 'api')

function filesBelow(root: string): string[] {
  return readdirSync(root).flatMap((name) => {
    if (['.next', 'coverage', 'node_modules', 'playwright-report', 'test-results'].includes(name)) return []
    const path = join(root, name)
    return statSync(path).isDirectory() ? filesBelow(path) : [path]
  })
}

describe('dashboard server architecture', () => {
  it('keeps every private API route behind the shared authentication guards', () => {
    const violations: string[] = []
    for (const path of filesBelow(apiRoot).filter((candidate) => candidate.endsWith('/route.ts'))) {
      const source = readFileSync(path, 'utf8')
      const name = relative(dashboardRoot, path)
      if (!source.includes('lib/server/auth')) {
        violations.push(`${name}: does not import the canonical server auth module`)
        continue
      }

      const isLogin = name === 'app/(dashboard)/api/auth/login/route.ts'
      const isLogout = name === 'app/(dashboard)/api/auth/logout/route.ts'
      const isSignup = name === 'app/(dashboard)/api/auth/signup/route.ts'
      if (isLogin || isLogout || isSignup) {
        if (
          !source.includes(isLogin ? 'isSameOriginRequest' : isLogout ? 'isSameOriginLogoutRequest' : 'isSameOriginRequest')
        ) {
          violations.push(`${name}: does not enforce its same-origin auth flow`)
        }
        continue
      }

      if (!source.includes('dashboardAuthErrorResponse') && !source.includes('dashboardMutationAuthErrorResponse')) {
        violations.push(`${name}: does not enforce dashboard authentication`)
      }
      if (/export async function (POST|PUT|PATCH|DELETE)\b/.test(source) && !source.includes('dashboardMutationAuthErrorResponse')) {
        violations.push(`${name}: mutation does not use the same-origin guard`)
      }
    }
    expect(violations).toEqual([])
  })

  it('allows child processes only through the shared Python bridge', () => {
    const violations = filesBelow(dashboardRoot)
      .filter((path) => /\.(ts|tsx)$/.test(path))
      .filter((path) => !path.endsWith('.test.ts') && !path.endsWith('.test.tsx'))
      .filter((path) => readFileSync(path, 'utf8').includes('node:child_process'))
      .map((path) => relative(dashboardRoot, path))
      .filter((path) => path !== 'lib/server/python-bridge.ts')
    expect(violations).toEqual([])
  })
})
