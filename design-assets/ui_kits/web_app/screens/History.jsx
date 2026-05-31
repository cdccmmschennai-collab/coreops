/* Report history — filterable, searchable table */

function History() {
  const [tab, setTab] = useState("all");
  const [filters, setFilters] = useState({ team: "Platform", date: "This week" });
  const all = REPORTS;
  const rows = tab === "all" ? all : all.filter((r) => r.status === tab);

  return (
    <>
      <PageHeader
        title="My reports"
        sub="Search, filter and export your daily reports."
        actions={
          <>
            <Button variant="secondary" icon="download">Export CSV</Button>
            <Button variant="primary" icon="plus">New report</Button>
          </>
        }
      />

      <Tabs
        value={tab} onChange={setTab}
        items={[
          { value: "all", label: "All", count: all.length },
          { value: "submitted", label: "Submitted", count: all.filter((r) => r.status === "submitted").length },
          { value: "in review", label: "In review", count: all.filter((r) => r.status === "in review").length },
          { value: "draft", label: "Drafts", count: all.filter((r) => r.status === "draft").length },
        ]}
      />

      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", margin: "16px 0" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "0 12px", height: 32, background: "#fff", border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", width: 280, fontSize: 13 }}>
          <Icon name="search" size={14} style={{ color: "var(--fg-3)" }} />
          <span style={{ color: "var(--fg-4)" }}>Search…</span>
        </div>
        {Object.entries(filters).map(([k, v]) => (
          <FilterChip key={k} k={k} v={v} onRemove={() => setFilters(({[k]: _, ...rest}) => rest)} />
        ))}
        <FilterChip k="Project" placeholder onRemove={() => {}} />
        <FilterChip k="Status" placeholder onRemove={() => {}} />
        <button className="btn btn-link" style={{ marginLeft: "auto" }}>Clear all</button>
      </div>

      <Card style={{ padding: 0 }}>
        <table className="table">
          <thead>
            <tr>
              <th style={{ width: 28 }}><input type="checkbox" /></th>
              <th>Report</th>
              <th>Project</th>
              <th>Submitted</th>
              <th>Hours</th>
              <th>Reviewer</th>
              <th>Status</th>
              <th style={{ width: 32 }}></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} className={i === 1 ? "selected" : ""}>
                <td><input type="checkbox" defaultChecked={i === 1} /></td>
                <td>
                  <div style={{ fontWeight: 500 }}>{r.title}</div>
                  <div style={{ color: "var(--fg-3)", fontSize: 11 }}>{r.entries} entries · {r.preview}</div>
                </td>
                <td>{r.project}</td>
                <td className="mono" style={{ color: "var(--fg-2)" }}>{r.date}<br /><span style={{ fontSize: 11, color: "var(--fg-3)" }}>{r.time}</span></td>
                <td className="mono">{r.hours}</td>
                <td>{r.reviewer ? <div style={{ display: "flex", alignItems: "center", gap: 6 }}><Avatar name={r.reviewer} size={20} /><span style={{ fontSize: 12 }}>{r.reviewer.split(" ")[0]}</span></div> : <span style={{ color: "var(--fg-4)" }}>—</span>}</td>
                <td><Badge variant={STATUS_VAR[r.status]}>{r.status}</Badge></td>
                <td><button className="icon-btn"><Icon name="more-horizontal" size={14} /></button></td>
              </tr>
            ))}
          </tbody>
        </table>
        <div style={{ padding: "12px 16px", display: "flex", alignItems: "center", justifyContent: "space-between", borderTop: "1px solid var(--border-subtle)", background: "var(--bg-surface-muted)", fontSize: 12, color: "var(--fg-3)" }}>
          <span>Showing 1–8 of 48</span>
          <div style={{ display: "flex", gap: 4 }}>
            <button className="btn btn-secondary btn-sm" disabled>‹ Prev</button>
            <button className="btn btn-secondary btn-sm">Next ›</button>
          </div>
        </div>
      </Card>
    </>
  );
}

function FilterChip({ k, v, placeholder, onRemove }) {
  const applied = !placeholder;
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 6, height: 28, padding: "0 10px",
      borderRadius: "var(--radius-full)", fontSize: 12,
      background: applied ? "var(--blue-50)" : "#fff",
      border: `1px solid ${applied ? "var(--blue-100)" : "var(--border)"}`,
      color: applied ? "var(--blue-700)" : "var(--fg-1)",
    }}>
      <span style={{ color: applied ? "var(--blue-700)" : "var(--fg-2)" }}>{k}{applied ? ":" : ""}</span>
      {applied ? <span style={{ fontWeight: 500 }}>{v}</span> : <Icon name="chevron-down" size={12} />}
      {applied && <span style={{ cursor: "pointer", color: applied ? "var(--blue-700)" : "var(--fg-3)" }} onClick={onRemove}>×</span>}
    </span>
  );
}

const STATUS_VAR = { submitted: "success", "in review": "info", draft: "neutral", approved: "success", blocked: "danger" };

const REPORTS = [
  { title: "May 24 — daily", entries: 2, preview: "Review queue · API refactor",  project: "WorkTrack Web",   date: "May 24", time: "4:32 PM", hours: "4h 45m", reviewer: "Marco Velez", status: "in review" },
  { title: "May 23 — daily", entries: 3, preview: "Shipped bulk approve",          project: "WorkTrack Web",   date: "May 23", time: "5:18 PM", hours: "7h 45m", reviewer: "Marco Velez", status: "submitted" },
  { title: "May 22 — daily", entries: 4, preview: "Token system, design review",   project: "WorkTrack Web",   date: "May 22", time: "4:50 PM", hours: "8h 10m", reviewer: "Marco Velez", status: "approved" },
  { title: "May 21 — daily", entries: 2, preview: "API refactor with Jordan",      project: "Mobile",        date: "May 21", time: "5:02 PM", hours: "6h 05m", reviewer: "Marco Velez", status: "approved" },
  { title: "May 20 — daily", entries: 3, preview: "Sprint planning · onboarding",  project: "Onboarding",    date: "May 20", time: "5:30 PM", hours: "7h 15m", reviewer: "Marco Velez", status: "approved" },
  { title: "May 19 — daily", entries: 2, preview: "Q3 planning prep",              project: "Q3 Planning",   date: "May 19", time: "5:10 PM", hours: "6h 40m", reviewer: "Marco Velez", status: "approved" },
  { title: "May 18 — draft", entries: 1, preview: "Wrote what I did in the AM",    project: "WorkTrack Web",   date: "May 18", time: "—",       hours: "1h 20m", reviewer: null,          status: "draft" },
  { title: "May 17 — daily", entries: 3, preview: "Onboarding spec review",        project: "Onboarding",    date: "May 17", time: "4:40 PM", hours: "3h 00m", reviewer: "Marco Velez", status: "approved" },
];

window.History = History;
