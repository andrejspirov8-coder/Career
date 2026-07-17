export type GlobalSearchResult = {
  kind: 'opportunity' | 'recruiter' | 'cv'
  id: string
  title: string
  subtitle: string
  href: string
}

export type GlobalSearchResponse = {
  query: string
  results: GlobalSearchResult[]
}
