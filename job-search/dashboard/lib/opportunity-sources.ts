import type { OpportunityConfig } from './opportunity-source-types'
import { runPythonHelper } from './server/python-bridge'

export type { OpportunityConfig } from './opportunity-source-types'

export async function getOpportunitySources(): Promise<OpportunityConfig> {
  return runPythonHelper<OpportunityConfig>('opportunitySources', ['show'], {
    timeoutMs: 15_000,
    errorLabel: 'Opportunity sources',
  })
}

export async function saveOpportunitySources(value: unknown): Promise<OpportunityConfig> {
  return runPythonHelper<OpportunityConfig>('opportunitySources', ['save', '--json', JSON.stringify(value)], {
    timeoutMs: 15_000,
    errorLabel: 'Opportunity sources',
  })
}
