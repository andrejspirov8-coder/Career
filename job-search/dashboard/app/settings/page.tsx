import Link from 'next/link'

import { getAutomationOverview } from '../../lib/automation-data'
import { getCvLibrary } from '../../lib/cv-data'
import { requireDashboardPageAuth } from '../../lib/dashboard-page-auth'
import { getDashboardOverview } from '../../lib/repo-data'
import { getSearchPreferences } from '../../lib/search-preferences'
import { getWorkspaceControlStatus } from '../../lib/workspace-control'
import type { WorkspaceControlStatus } from '../../lib/workspace-control-types'
import { getLocalDraftingStatus } from '../../lib/local-drafting'
import type { LocalDraftingStatus } from '../../lib/local-drafting-types'
import LocalDraftingSettings from './local-drafting-settings'
import SearchProfileForm from './search-profile-form'
import SystemControls from './system-controls'

export const dynamic = 'force-dynamic'

function unavailableWorkspaceControls(): WorkspaceControlStatus {
  return {
    schema: 'career_workspace_controls_v1',
    generated_at: new Date().toISOString(),
    dashboard: { built_at: '', latest_source_modified_at: '', update_available: false, restart_supported: false, last_restart_error: '', status: 'unknown' },
    keychain: { supported: false, configured: true, storage: 'environment' },
    startup: { supported: false, installed: false, loaded: false, path: '' },
    backup: { supported: false, directory: '', minimum_passphrase_length: 12, restore_available: false, backups: [] },
  }
}

function unavailableDraftingStatus(): LocalDraftingStatus {
  return {
    schema: 'career_local_drafting_status_v1',
    enabled: false,
    model: 'qwen3.5:35b-a3b-fast',
    provider: 'local_ollama',
    network_scope: '127.0.0.1 only',
    dashboard_stores_prompts: false,
    automatic_actions: false,
    ollama: { online: false, models: [], base_url: 'http://127.0.0.1:11434', message: 'Local drafting status is unavailable.' },
  }
}

export default async function SettingsPage() {
  await requireDashboardPageAuth('/settings')
  const [overview, automation, searchPreferences, workspaceControls, draftingStatus, cvs] = await Promise.all([
    getDashboardOverview(),
    getAutomationOverview().catch(() => null),
    getSearchPreferences(),
    getWorkspaceControlStatus().catch(unavailableWorkspaceControls),
    getLocalDraftingStatus().catch(unavailableDraftingStatus),
    getCvLibrary(),
  ])

  return (
    <main className="workspaceMain">
      <div className="workspaceHeading">
        <div>
          <div className="eyebrow">Local workspace</div>
          <h1>Settings</h1>
          <p className="muted">Privacy, scheduling, data export, and technical health.</p>
        </div>
        <div className={`serviceIndicator ${automation?.worker.online ? 'online' : ''}`}>
          <span aria-hidden="true" />
          <div>
            <strong>{automation?.worker.online ? 'Service running' : 'Service on demand'}</strong>
            <small>127.0.0.1 only</small>
          </div>
        </div>
      </div>

      <div className="settingsGrid">
        <SearchProfileForm initialPreferences={searchPreferences} />

        <section className="workspacePanel settingsPanel">
          <div className="panelHeading">
            <div><div className="eyebrow">Privacy</div><h2>Local and locked</h2><p>Private career data stays on this Mac.</p></div>
          </div>
          <div className="settingsRows">
            <SettingRow label="Network access" value="This Mac only" detail="The server binds to 127.0.0.1." />
            <SettingRow label="Browser session" value="Private cookie" detail="The original dashboard secret is never stored in the browser." />
            <SettingRow label="Applications" value="Manual only" detail="The app prepares and records; it never submits." />
            <SettingRow label="LinkedIn" value="Human-controlled" detail="Search and sending are excluded from scheduled web automation." />
          </div>
        </section>

        <section className="workspacePanel settingsPanel">
          <div className="panelHeading">
            <div><div className="eyebrow">Daily routine</div><h2>Schedule</h2><p>Runs only while the local service is open.</p></div>
          </div>
          <div className="settingsRows">
            <SettingRow label="Daily search" value={automation?.settings.schedule_enabled ? `On at ${automation.settings.schedule_time}` : 'Off'} detail="Europe/Vilnius timezone" />
            <SettingRow label="Background worker" value={automation?.worker.online ? 'Online' : 'Starts when needed'} detail="Your Mac must be awake and online." />
          </div>
          <Link className="buttonLink" href="/automation">Change schedule</Link>
        </section>

        <section className="workspacePanel settingsPanel">
          <div className="panelHeading">
            <div><div className="eyebrow">Your data</div><h2>Backup and export</h2><p>Download a readable JSON copy of opportunities, evidence, actions, and applications.</p></div>
          </div>
          <div className="settingsRows">
            <SettingRow label="Applications logged" value={String(overview.counts.applicationRows)} detail="Stored in the local application log." />
            <SettingRow label="Application packs" value={String(overview.counts.packs)} detail="Stored under the private project folder." />
            <SettingRow label="CV PDFs" value={`${cvs.counts.readyPdfs}/${cvs.counts.expectedPdfs}`} detail="Visual and ATS formats." />
          </div>
          <a className="buttonLink" href="/api/export">Download readable JSON export</a>
        </section>

        <SystemControls initialStatus={workspaceControls} />
        <LocalDraftingSettings initialStatus={draftingStatus} />
      </div>

      <details className="workspacePanel settingsAdvanced">
        <summary>Technical health</summary>
        <div className="systemColumns">
          <div className="systemList">
            {overview.workflowChecks.map((check) => (
              <div key={check.label}>
                <span className={`statusDot ${check.available ? 'status-succeeded' : 'status-failed'}`} aria-hidden="true" />
                <span><strong>{check.label}</strong><small>{check.detail}</small></span>
              </div>
            ))}
          </div>
          <div className="systemContext">
            <div><span>MCP service</span><strong>{overview.health.mcp.ok ? 'Online' : 'Optional / offline'}</strong></div>
            <div><span>Reports</span><strong>{overview.counts.summaryReports}</strong></div>
            <div><span>Recent files</span><strong>{overview.recentPipelineFiles.length}</strong></div>
            <div><span>CV variants</span><strong>{overview.counts.cvVariants}</strong></div>
          </div>
        </div>
      </details>
    </main>
  )
}

function SettingRow({ label, value, detail }: { label: string; value: string; detail: string }) {
  return <div><span>{label}</span><strong>{value}</strong><small>{detail}</small></div>
}
