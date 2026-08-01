export interface SetupStep {
  id: string
  label: string
  detail: string
  href: string
  done: boolean
}

export interface SetupChecklist {
  steps: SetupStep[]
  done_count: number
  total: number
  complete: boolean
}
