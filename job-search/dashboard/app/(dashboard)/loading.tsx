export default function Loading() {
  return (
    <main className="workspaceMain">
      <div className="workspaceHeading todayHeading">
        <div>
          <div className="skeleton" style={{ width: 100, height: 14, marginBottom: 9 }} />
          <div className="skeleton" style={{ width: 320, height: 42, marginBottom: 10 }} />
          <div className="skeleton" style={{ width: 260, height: 16 }} />
        </div>
      </div>

      <section className="briefingHero">
        <div>
          <div className="skeleton" style={{ width: 100, height: 14, marginBottom: 9 }} />
          <div className="skeleton" style={{ width: 360, height: 24, marginBottom: 10 }} />
          <div className="skeleton" style={{ width: 420, height: 16, marginBottom: 16 }} />
          <div className="dailyProgress">
            <div className="skeleton" style={{ width: '60%', height: 16 }} />
            <div className="dailyProgressTrack" aria-hidden="true">
              <div className="skeleton" style={{ width: '33%', height: 8 }} />
            </div>
          </div>
        </div>
        <div className="skeleton" style={{ width: 180, height: 48, borderRadius: 9 }} />
      </section>

      <section className="briefingChecklist" aria-label="Today at a glance">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="skeleton" style={{ height: 72, borderRadius: 12 }} />
        ))}
      </section>

      <div className="briefingGrid">
        <section className="workspacePanel briefingShortlist">
          <div className="panelHeading">
            <div>
              <div className="skeleton" style={{ width: 80, height: 14, marginBottom: 8 }} />
              <div className="skeleton" style={{ width: 200, height: 20, marginBottom: 6 }} />
              <div className="skeleton" style={{ width: 300, height: 14 }} />
            </div>
          </div>
          {[1, 2, 3].map((i) => (
            <div key={i} className="skeleton" style={{ width: '100%', height: 52, marginTop: 10, borderRadius: 8 }} />
          ))}
        </section>

        <section className="workspacePanel briefingSafety">
          <div className="panelHeading">
            <div>
              <div className="skeleton" style={{ width: 80, height: 14, marginBottom: 8 }} />
              <div className="skeleton" style={{ width: 240, height: 20, marginBottom: 6 }} />
              <div className="skeleton" style={{ width: 280, height: 14 }} />
            </div>
          </div>
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="skeleton" style={{ width: '100%', height: 36, marginTop: 8, borderRadius: 6 }} />
          ))}
        </section>
      </div>
    </main>
  )
}
