import type { SetupChecklist } from './setup-checklist-types'
import { runPythonHelper } from './server/python-bridge'

export type { SetupChecklist } from './setup-checklist-types'

export async function getSetupChecklist(): Promise<SetupChecklist> {
  return runPythonHelper<SetupChecklist>('setupChecklist', ['check'], {
    timeoutMs: 15_000,
    errorLabel: 'Setup checklist',
  })
}
