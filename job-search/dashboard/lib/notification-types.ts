export type NotificationPriority = 'urgent' | 'attention' | 'info'
export type NotificationCategory = 'automation' | 'opportunity' | 'application' | 'development' | 'system'
export type NotificationScope = 'automation' | 'opportunity' | 'application' | 'development'
export type NotificationKind =
  | 'automation_completed'
  | 'strong_role'
  | 'application_deadline'
  | 'follow_up_due'
  | 'source_health'
  | 'schedule_missed'
  | 'dev_proposals_ready'
  | 'dev_agent_failed'
  | 'dev_auto_apply_succeeded'
  | 'dev_autonomy_paused'
  | 'dev_model_requalification'

export type NotificationCandidate = {
  notification_id: string
  scope: NotificationScope
  category: NotificationCategory
  kind: NotificationKind
  priority: NotificationPriority
  lifecycle: 'event' | 'condition'
  title: string
  body: string
  href: string
  occurred_at: string
  source_updated_at: string | null
  desktop_eligible: boolean
}

export type CareerNotification = {
  notification_id: string
  category: NotificationCategory
  kind: NotificationKind
  priority: NotificationPriority
  title: string
  body: string
  href: string
  occurred_at: string
  read_at: string | null
  dismissed_at: string | null
  snoozed_until: string | null
  resolved_at: string | null
  desktop_delivered_at: string | null
  is_unread: boolean
  is_snoozed: boolean
}

export type NotificationOverview = {
  schema: 'career_notification_overview_v1'
  generated_at: string
  counts: {
    active: number
    unread: number
    urgent: number
    attention: number
    snoozed: number
    archived: number
  }
  inbox: CareerNotification[]
  snoozed: CareerNotification[]
  archived: CareerNotification[]
  desktop_pending: CareerNotification[]
  settings: {
    desktop_enabled: boolean
    updated_at: string
  }
}

export type NotificationIndividualAction =
  | 'read'
  | 'unread'
  | 'dismiss'
  | 'restore'
  | 'snooze_day'
  | 'snooze_week'
  | 'clear_snooze'

export type NotificationActionInput =
  | { action: NotificationIndividualAction; notification_id: string }
  | { action: 'read_all' }
  | { action: 'set_desktop'; enabled: boolean; mark_existing: boolean }
  | { action: 'desktop_delivered'; notification_ids: string[] }
