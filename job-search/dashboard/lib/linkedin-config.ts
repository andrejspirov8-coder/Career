import type { LinkedInConfig } from './linkedin-config-types'
import { runFastApiHelper } from './server/fastapi-bridge'

export type { LinkedInConfig } from './linkedin-config-types'

export async function getLinkedInConfig(): Promise<LinkedInConfig> {
  return runFastApiHelper<LinkedInConfig>('linkedinConfig', ['show'], {
    timeoutMs: 15_000,
    errorLabel: 'LinkedIn config',
  })
}

export async function saveLinkedInConfig(value: unknown): Promise<LinkedInConfig> {
  return runFastApiHelper<LinkedInConfig>('linkedinConfig', ['save', '--json', JSON.stringify(value)], {
    timeoutMs: 15_000,
    errorLabel: 'LinkedIn config',
  })
}
