export function isOpportunityId(value: unknown): value is string {
  return typeof value === 'string' && /^opp_[A-Za-z0-9_-]{1,128}$/.test(value)
}
