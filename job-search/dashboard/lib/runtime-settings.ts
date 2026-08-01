import type { RuntimeSettings } from './runtime-settings-types'
import { runFastApiHelper } from './server/fastapi-bridge'

export type { RuntimeSettings } from './runtime-settings-types'

export async function getRuntimeSettings(): Promise<RuntimeSettings> {
  return runFastApiHelper<RuntimeSettings>('settingsControl', ['show'], {
    timeoutMs: 15_000,
    errorLabel: 'Runtime settings',
  })
}

export async function saveRuntimeSettings(value: unknown): Promise<RuntimeSettings> {
  return runFastApiHelper<RuntimeSettings>('settingsControl', ['save', '--json', JSON.stringify(value)], {
    timeoutMs: 15_000,
    errorLabel: 'Runtime settings',
  })
}
