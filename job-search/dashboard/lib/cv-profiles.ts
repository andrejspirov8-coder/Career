import type { VariantProfilesConfig } from './cv-profiles-types'
import { runFastApiHelper } from './server/fastapi-bridge'

export type { VariantProfilesConfig, VariantProfile } from './cv-profiles-types'

export async function getCvProfiles(): Promise<VariantProfilesConfig> {
  return runFastApiHelper<VariantProfilesConfig>('cvProfiles', ['show'], {
    timeoutMs: 15_000,
    errorLabel: 'CV profiles',
  })
}

export async function saveCvProfiles(value: unknown): Promise<VariantProfilesConfig> {
  return runFastApiHelper<VariantProfilesConfig>('cvProfiles', ['save', '--json', JSON.stringify(value)], {
    timeoutMs: 15_000,
    errorLabel: 'CV profiles',
  })
}
