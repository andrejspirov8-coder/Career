export type WorkspaceBackup = {
  filename: string
  size_bytes: number
  created_at: string
  pre_restore: boolean
}

export type DashboardBuildStatus = {
  built_at: string
  latest_source_modified_at: string
  update_available: boolean
  restart_supported: boolean
  last_restart_error: string
  status: 'current' | 'update_available' | 'unknown'
}

export type DashboardRuntimeStatus = {
  latest_source_modified_at: string
  restart_supported: boolean
  last_restart_error: string
}

export type WorkspaceControlStatus = {
  schema: 'career_workspace_controls_v1'
  generated_at: string
  dashboard: DashboardBuildStatus
  keychain: {
    supported: boolean
    configured: boolean
    storage: 'keychain' | 'env_file' | 'environment' | 'missing'
  }
  startup: {
    supported: boolean
    installed: boolean
    loaded: boolean
    path: string
  }
  backup: {
    supported: boolean
    directory: string
    minimum_passphrase_length: number
    restore_available: boolean
    backups: WorkspaceBackup[]
  }
}

export type WorkspaceControlAction =
  | 'dashboard-restart'
  | 'keychain-enable'
  | 'keychain-disable'
  | 'startup-enable'
  | 'startup-disable'
  | 'backup-create'
  | 'backup-validate'
  | 'backup-restore'

export type BackupActionResult = {
  filename: string
  created_at?: string
  file_count?: number
  data_bytes?: number
  encrypted_bytes?: number
  valid?: boolean
  restored_files?: number
  safety_backup?: string
  mode?: 'overlay'
}

export type DashboardRestartResult = {
  requested: boolean
  request_id: string
  message: string
}
