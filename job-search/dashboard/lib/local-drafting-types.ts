export type LocalDraftingStatus = {
  schema: 'career_local_drafting_status_v1'
  enabled: boolean
  model: string
  provider: 'local_ollama'
  network_scope: '127.0.0.1 only'
  dashboard_stores_prompts: false
  automatic_actions: false
  ollama: {
    online: boolean
    models: string[]
    base_url: 'http://127.0.0.1:11434'
    message: string
  }
}

export type LocalDraftType = 'cover_letter' | 'follow_up'

export type LocalDraftResult = {
  draft_type: LocalDraftType
  text: string
  model: string
  recommended_cv_variant: string
  privacy: {
    provider: 'local_ollama'
    sent_to: 'http://127.0.0.1:11434'
    stored_by_dashboard: false
    automatic_send: false
  }
  warning: string
}
