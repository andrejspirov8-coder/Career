export default function Loading() {
  return (
    <main className="workspaceMain">
      <div className="workspaceHeading">
        <div>
          <div className="skeleton" style={{ width: 140, height: 14, marginBottom: 8 }} />
          <div className="skeleton" style={{ width: 280, height: 42, marginBottom: 8 }} />
          <div className="skeleton" style={{ width: 200, height: 16 }} />
        </div>
      </div>

      <section className="pipelineOverview">
        <div className="funnelBand">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <div key={i} className="skeleton" style={{ height: 48, borderRadius: 8 }} />
          ))}
        </div>
      </section>

      <section className="pipelineStages" aria-label="Application stages">
        {[1, 2, 3, 4, 5, 6, 7, 8].map((i) => (
          <div key={i} className="skeleton" style={{ width: 100, height: 36, borderRadius: 8 }} />
        ))}
      </section>

      <section className="triageLayout opportunityTriage">
        <div className="queueList">
          <div className="queueListHeading">
            <div className="skeleton" style={{ width: '40%', height: 20 }} />
          </div>
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="skeleton" style={{ width: '100%', height: 82, borderRadius: 8 }} />
          ))}
        </div>
        <aside className="detailPanel">
          <div className="skeleton" style={{ width: 100, height: 14, marginBottom: 8 }} />
          <div className="skeleton" style={{ width: '80%', height: 22, marginBottom: 12 }} />
          <div className="skeleton" style={{ width: '100%', height: 120, borderRadius: 8 }} />
          <div className="skeleton" style={{ width: '100%', height: 80, borderRadius: 8, marginTop: 12 }} />
        </aside>
      </section>
    </main>
  )
}
