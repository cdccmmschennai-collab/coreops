/* Project tracking — project hub: contributors, status, recent reports */

function ProjectDetail({ onNavigate }) {
  return (
    <>
      <div style={{ marginBottom: 20 }}>
        <a className="btn btn-link" onClick={() => onNavigate("dashboard")} style={{ padding: 0, fontSize: 12 }}>← Projects</a>
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 16, marginTop: 8 }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span style={{ width: 12, height: 12, borderRadius: 3, background: "var(--chart-1)" }} />
              <h1 style={{ margin: 0, fontSize: 22, fontWeight: 600, letterSpacing: "-0.01em" }}>WorkTrack Web · sprint 14</h1>
              <Badge variant="success">active</Badge>
            </div>
            <div style={{ fontSize: 13, color: "var(--fg-2)", marginTop: 6 }}>
              <span className="mono">WT-WEB-14</span> · led by Marco Velez · 8 contributors · ends May 31
            </div>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <Button variant="secondary" icon="users">Manage members</Button>
            <Button variant="secondary" icon="settings">Settings</Button>
            <Button variant="primary" icon="plus">Log time</Button>
          </div>
        </div>
      </div>

      <div className="kpi-grid" style={{ marginBottom: 24, gridTemplateColumns: "repeat(4, 1fr)" }}>
        <Kpi label="Hours logged" value="282h" delta={{ dir: "up", text: "88% of allocation" }} />
        <Kpi label="Reports this week" value="34" />
        <Kpi label="Open blockers" value="2" delta={{ dir: "down", text: "−1" }} />
        <Kpi label="On-time rate" value="94%" delta={{ dir: "up", text: "+2%" }} />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 2fr) minmax(0, 1fr)", gap: 16 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <Card>
            <CardHeader title="Burn down" meta="282h / 320h" />
            <CardBody><BurnChart /></CardBody>
          </Card>

          <Card>
            <CardHeader title="Recent reports" action={<Button variant="ghost" size="sm">View all →</Button>} />
            <table className="table">
              <thead><tr><th>Contributor</th><th>Date</th><th>Hours</th><th>Summary</th><th>Status</th></tr></thead>
              <tbody>
                {PROJ_REPORTS.map((r, i) => (
                  <tr key={i}>
                    <td><div style={{ display: "flex", alignItems: "center", gap: 8 }}><Avatar name={r.name} size={22} /><span>{r.name}</span></div></td>
                    <td className="mono" style={{ color: "var(--fg-2)" }}>{r.date}</td>
                    <td className="mono">{r.hours}</td>
                    <td style={{ color: "var(--fg-2)", maxWidth: 280, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.summary}</td>
                    <td><Badge variant={r.statusVar}>{r.status}</Badge></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <Card>
            <CardHeader title="Contributors" meta="8" />
            <div>
              {CONTRIBUTORS.map((c, i) => (
                <div key={i} style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 16px", borderBottom: i < CONTRIBUTORS.length - 1 ? "1px solid var(--border-subtle)" : "0" }}>
                  <Avatar name={c.name} size={28} presence={c.online ? "online" : null} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 500 }}>{c.name}</div>
                    <div style={{ fontSize: 11, color: "var(--fg-3)" }}>{c.role}</div>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <div className="mono" style={{ fontSize: 12 }}>{c.hours}</div>
                    <div style={{ fontSize: 10, color: "var(--fg-3)" }} className="mono">this sprint</div>
                  </div>
                </div>
              ))}
            </div>
          </Card>

          <Card>
            <CardHeader title="Blockers" meta="2 open" />
            <div>
              <div style={{ padding: "12px 16px", borderBottom: "1px solid var(--border-subtle)" }}>
                <div style={{ fontSize: 13, fontWeight: 500 }}>Design tokens not finalized</div>
                <div style={{ fontSize: 11, color: "var(--fg-3)", marginTop: 2 }}>Priya R · open 2 days</div>
              </div>
              <div style={{ padding: "12px 16px" }}>
                <div style={{ fontSize: 13, fontWeight: 500 }}>Auth refactor PR blocked on review</div>
                <div style={{ fontSize: 11, color: "var(--fg-3)", marginTop: 2 }}>Jordan K · open 4h</div>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </>
  );
}

const CONTRIBUTORS = [
  { name: "Marco Velez",     role: "Lead",            hours: "12h",  online: true },
  { name: "Priya Ramanujan", role: "Senior Engineer", hours: "32h",  online: true },
  { name: "Lin Chen",        role: "Engineer",        hours: "22h",  online: false },
  { name: "Hassan Al-Awar",  role: "Senior Engineer", hours: "33h",  online: false },
  { name: "Riya Shah",       role: "Engineer",        hours: "12h",  online: false },
];

const PROJ_REPORTS = [
  { name: "Priya Ramanujan", date: "May 24", hours: "4h 45m", summary: "Review queue and bulk approve shipped", status: "in review", statusVar: "info" },
  { name: "Jordan Kim",      date: "May 24", hours: "8h 10m", summary: "Auth refactor PR opened",               status: "submitted", statusVar: "success" },
  { name: "Lin Chen",        date: "May 23", hours: "7h 00m", summary: "Onboarding empty states",               status: "approved",  statusVar: "success" },
  { name: "Hassan Al-Awar",  date: "May 23", hours: "6h 50m", summary: "Performance regression triage",         status: "approved",  statusVar: "success" },
  { name: "Riya Shah",       date: "May 22", hours: "—",      summary: "On leave",                               status: "n/a",       statusVar: "neutral" },
];

function BurnChart() {
  // ideal vs actual over 14 days
  const days = 14;
  const ideal = Array.from({ length: days + 1 }, (_, i) => 320 - (320 / days) * i);
  const actual = [320, 308, 295, 282, 268, 255, 240, 226, 210, 196, 182, 166];
  const w = 580, h = 180, pad = 28;
  const max = 320, min = 0;
  const xfor = (i) => pad + (i / days) * (w - pad * 2);
  const yfor = (v) => pad + (1 - (v - min) / (max - min)) * (h - pad * 2);
  const idealD = ideal.map((v, i) => `${i === 0 ? "M" : "L"}${xfor(i)},${yfor(v)}`).join(" ");
  const actD = actual.map((v, i) => `${i === 0 ? "M" : "L"}${xfor(i)},${yfor(v)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${w} ${h + 6}`} width="100%" style={{ display: "block" }}>
      <g stroke="var(--border-subtle)" strokeDasharray="2 3" fill="none">
        {[0.2, 0.5, 0.8].map((p, i) => <line key={i} x1={pad} y1={pad + p * (h - pad * 2)} x2={w - pad} y2={pad + p * (h - pad * 2)} />)}
      </g>
      <g fontFamily="Geist Mono, monospace" fontSize="9" fill="var(--fg-3)">
        <text x="6" y={pad + 4}>320</text>
        <text x="6" y={pad + 0.5 * (h - pad * 2) + 4}>160</text>
        <text x="6" y={h - pad + 4}>0</text>
      </g>
      <path d={idealD} stroke="var(--fg-4)" strokeDasharray="4 4" strokeWidth="1.5" fill="none" />
      <path d={actD} stroke="var(--chart-1)" strokeWidth="2" fill="none" />
      {actual.map((v, i) => <circle key={i} cx={xfor(i)} cy={yfor(v)} r="2.5" fill="var(--chart-1)" />)}
      {/* labels */}
      <g fontFamily="Geist Mono, monospace" fontSize="10" fill="var(--fg-3)">
        <rect x={w - pad - 110} y={pad - 2} width="118" height="18" rx="4" fill="#fff" />
        <circle cx={w - pad - 102} cy={pad + 7} r="3" fill="var(--chart-1)" />
        <text x={w - pad - 96} y={pad + 10}>actual</text>
        <line x1={w - pad - 60} y1={pad + 7} x2={w - pad - 44} y2={pad + 7} stroke="var(--fg-4)" strokeDasharray="3 3" strokeWidth="1.5" />
        <text x={w - pad - 40} y={pad + 10}>ideal</text>
      </g>
    </svg>
  );
}

window.ProjectDetail = ProjectDetail;
