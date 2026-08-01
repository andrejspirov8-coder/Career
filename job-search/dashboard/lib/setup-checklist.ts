import type { SetupChecklist } from './setup-checklist-types'
import { runFastApiHelper } from './server/fastapi-bridge'

export type { SetupChecklist } from './setup-checklist-types'

export async function getSetupChecklist(): Promise<SetupChecklist> {
  return runFastApiHelper<SetupChecklist>('setupChecklist', ['check'], {
    timeoutMs: 15_000,
    errorLabel: 'Setup checklist',
  })
}
