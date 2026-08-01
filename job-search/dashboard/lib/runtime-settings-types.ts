export interface RuntimeSettings {
  runtime: {
    mode: string
    dry_run_default: boolean
    require_live_dispatch_ack: boolean
    require_approval_ledger: boolean
  }
  limits: {
    max_live_dispatch_batch: number
    stop_on_captcha: boolean
    stop_on_checkpoint: boolean
    stop_on_unusual_activity: boolean
  }
  state: {
    database_path: string
    export_csv: boolean
  }
}
