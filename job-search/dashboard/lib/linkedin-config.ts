import type { LinkedInConfig } from './linkedin-config-types'
import { runPythonHelper } from './server/python-bridge'

export type { LinkedInConfig } from './linkedin-config-types'

export async function getLinkedInConfig(): Promise<LinkedInConfig> {
  return runPythonHelper<LinkedInConfig>('linkedinConfig', ['show'], {
    timeoutMs: 15_000,
    errorLabel: 'LinkedIn config',
  })
}

export async function saveLinkedInConfig(value: unknown): Promise<LinkedInConfig> {
  return runPythonHelper<LinkedInConfig>('linkedinConfig', ['save', '--json', JSON.stringify(value)], {
    timeoutMs: 15_000,
    errorLabel: 'LinkedIn config',
  })
}
