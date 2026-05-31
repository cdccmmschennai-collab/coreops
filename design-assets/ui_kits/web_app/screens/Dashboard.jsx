/* Employee Dashboard — today + this week + recent + projects */

function Dashboard({ onNavigate }) {
  return (
    <>
      <PageHeader
        title="Good afternoon, Priya"
        sub="Friday, May 24 · You have 1 report due today"
        actions={
          <>
            <Button variant="secondary" icon="calendar">This week</Button>
            <Button variant="primary" icon="plus" onClick={() => onNavigate("report")}>New report</Button>
          </>
        }
      />

      <div className="kpi-grid" style={{ marginBottom: 24 }}>
        <Kpi label="Hours logged this week" value="32h 15m" delta={{ dir: "up", text: "+2h vs last week" }} />
        <Kpi label="Reports submitted" value="4 / 5" delta={{ dir: "up", text: "on track" }} />
        <Kpi label="In review" value="2" />
        <Kpi label="Blockers" value="1" delta={{ dir: "down", text: "needs attention" }} />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 2fr) minmax(0, 1fr)", gap: 16 }}>
        <Card>
          <CardHeader title="Recent reports" action={<a className="btn btn-link" onClick={() => onNavigate("history")}>View all →</a>} />
          <table className="table">
            <thead>
              <tr>
                <th>Date</th><th>Project</th><th>Hours</th><th>Status</th>
              </tr>
            </thead>
            <tbody>
              {RECENT.map((r, i) => (
                <tr key={i} style={{ cursor: "pointer" }}>
                  <td><div style={{ fontWeight: 500 }}>{r.date}</div><div style={{ color: "var(--fg-3)", fontSize: 11 }}>{r.day}</div></td>
                  <td>{r.project}</td>
                  <td className="mono">{r.hours}</td>
                  <td><Badge variant={r.statusVar}>{r.status}</Badge></td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>

        <Card>
          <CardHeader title="My projects" />
          <div style={{ padding: 8 }}>
            {PROJECTS.map((p, i) => (
              <button key={i} className="nav-item" onClick={() => onNavigate("projects")} style={{ width: "100%", marginBottom: 2 }}>
                <span style={{ width: 8, height: 8, borderRadius: 2, background: p.color, flexShrink: 0 }} />
                <span style={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{p.name}</span>
                <span className="count">{p.hours}</span>
              </button>
            ))}
          </div>
        </Card>
      </div>

      <div style={{ marginTop: 16, display: "grid", gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1fr)", gap: 16 }}>
        <Card>
          <CardHeader title="Hours this week" meta="May 18 – 24" />
          <CardBody><WeekChart /></CardBody>
        </Card>
        <Card>
          <CardHeader title="Team activity" />
          <CardBody><Timeline /></CardBody>
        </Card>
      </div>
    </>
  );
}

const RECENT = [
  { date: "May 23", day: "Thu", project: "WorkTrack Web", hours: "7h 45m", status: "submitted", statusVar: "success" },
  { date: "May 22", day: "Wed", project: "WorkTrack Web", hours: "8h 10m", status: "in review", statusVar: "info" },
  { date: "May 21", day: "Tue", project: "Mobile · API", hours: "6h 05m", status: "approved", statusVar: "success" },
  { date: "May 20", day: "Mon", project: "WorkTrack Web", hours: "7h 15m", status: "approved", statusVar: "success" },
  { date: "May 17", day: "Fri", project: "Onboarding", hours: "3h 00m", status: "approved", statusVar: "success" },
];

const PROJECTS = [
  { name: "WorkTrack Web · sprint 14", hours: "18h", color: "var(--chart-1)" },
  { name: "Mobile · Reporting API",  hours: "9h",  color: "var(--chart-2)" },
  { name: "Onboarding redesign",     hours: "3h",  color: "var(--chart-3)" },
  { name: "Q3 planning",             hours: "2h",  color: "var(--chart-4)" },
];

function WeekChart() {
  const data = [
    { d: "M", a: 60, b: 20 },
    { d: "T", a: 70, b: 22 },
    { d: "W", a: 48, b: 22 },
    { d: "T", a: 62, b: 24 },
    { d: "F", a: 40, b: 14 },
    { d: "S", a: 0, b: 0 },
    { d: "S", a: 0, b: 0 },
  ];
  return (
    <svg viewBox="0 0 560 180" width="100%" style={{ display: "block" }}>
      <g stroke="var(--border-subtle)" strokeDasharray="2 3" fill="none">
        {[20, 60, 100, 140].map((y) => <line key={y} x1="36" y1={y} x2="556" y2={y} />)}
      </g>
      <g fontFamily="Geist Mono, monospace" fontSize="10" fill="var(--fg-3)" textAnchor="end">
        <text x="32" y="24">10h</text><text x="32" y="64">6h</text><text x="32" y="104">3h</text><text x="32" y="144">0</text>
      </g>
      {data.map((d, i) => {
        const x = 60 + i * 72;
        const aH = d.a * 1.4, bH = d.b * 1.4;
        const yA = 140 - aH, yB = yA - bH;
        return (
          <g key={i} transform={`translate(${x}, 0)`}>
            {d.a > 0 && <rect x="0" y={yA} width="44" height={aH} rx="3" fill="var(--chart-1)" opacity={i >= 5 ? 0.3 : 0.9} />}
            {d.b > 0 && <rect x="0" y={yB} width="44" height={bH} rx="3" fill="var(--chart-2)" opacity={i >= 5 ? 0.3 : 0.9} />}
            <text x="22" y="160" fontFamily="Geist Mono, monospace" fontSize="10" fill="var(--fg-3)" textAnchor="middle">{d.d}</text>
          </g>
        );
      })}
    </svg>
  );
}

function Timeline() {
  const items = [
    { who: "Priya", what: "submitted", obj: "May 24 daily", time: "4:32 PM", dot: "green" },
    { who: "Jordan", what: "requested review on", obj: "Mobile sprint 14", time: "3:48 PM", dot: "blue" },
    { who: "Ana", what: "opened", obj: "Project WorkTrack Web", time: "2:10 PM", dot: "neutral" },
    { who: "Marco", what: "reassigned 2 reports", obj: "to Lin", time: "11:42 AM", dot: "neutral" },
  ];
  const dotColor = { green: "var(--green-500)", blue: "var(--blue-500)", neutral: "var(--slate-300)" };
  return (
    <div style={{ position: "relative", paddingLeft: 20 }}>
      <div style={{ position: "absolute", left: 7, top: 6, bottom: 6, width: 1, background: "var(--border)" }} />
      {items.map((it, i) => (
        <div key={i} style={{ position: "relative", padding: "6px 0", display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ position: "absolute", left: -19, top: 11, width: 10, height: 10, borderRadius: "50%", background: "#fff", border: `2px solid ${dotColor[it.dot]}` }} />
          <span className="mono" style={{ fontSize: 11, color: "var(--fg-3)", width: 64 }}>{it.time}</span>
          <span style={{ fontSize: 13 }}>
            <span style={{ fontWeight: 500 }}>{it.who}</span>{" "}
            <span style={{ color: "var(--fg-2)" }}>{it.what}</span>{" "}
            <span style={{ color: "var(--fg-link)" }}>{it.obj}</span>
          </span>
        </div>
      ))}
    </div>
  );
}

window.Dashboard = Dashboard;
