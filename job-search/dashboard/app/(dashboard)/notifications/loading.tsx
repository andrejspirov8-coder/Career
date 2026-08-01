export default function Loading() {
  return (
    <main className="workspaceMain">
      <div className="workspaceHeading">
        <div>
          <div className="skeleton" style={{ width: 120, height: 14, marginBottom: 8 }} />
          <div className="skeleton" style={{ width: 240, height: 42 }} />
        </div>
      </div>

      <div className="triageLayout">
        <div className="queueList">
          <div className="queueListHeading">
            <div className="skeleton" style={{ width: '30%', height: 20 }} />
          </div>
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="skeleton" style={{ width: '100%', height: 64, borderRadius: 8 }} />
          ))}
        </div>
        <aside className="detailPanel">
          <div className="skeleton" style={{ width: 80, height: 14, marginBottom: 8 }} />
          <div className="skeleton" style={{ width: '70%', height: 22, marginBottom: 12 }} />
          <div className="skeleton" style={{ width: '100%', height: 80, borderRadius: 8 }} />
        </aside>
      </div>
    </main>
  )
}
