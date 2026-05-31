/* Team productivity — manager view */

function Team({ onNavigate }) {
  return (
    <>
      <PageHeader
        title="Team — Platform"
        sub="12 members · 9 reports submitted today · 3 pending review"
        actions={
          <>
            <Segmented value="week" onChange={() => {}} items={[
              { value: "day", label: "Day" }, { value: "week", label: "Week" }, { value: "month", label: "Month" },
            ]} />
            <Button variant="primary" icon="check-circle-2">Review queue · 3</Button>
          </>
        }
      />

      <div className="kpi-grid" style={{ marginBottom: 24 }}>
        <Kpi label="Avg hours / day" value="7h 24m" delta={{ dir: "up", text: "+12m" }} />
        <Kpi label="On-time rate" value="92%" delta={{ dir: "up", text: "+4%" }} />
        <Kpi label="Open blockers" value="2" />
        <Kpi label="Review SLA" value="4.2h" delta={{ dir: "down", text: "−0.8h" }} />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1.4fr) minmax(0, 1fr)", gap: 16, marginBottom: 16 }}>
        <Card>
          <CardHeader title="Hours by member this week" meta="May 18 – 24" />
          <CardBody>
            <TeamBars />
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Review queue" meta="3 reports" />
          <div>
            {REVIEWS.map((r, i) => (
              <div key={i} style={{ padding: "12px 16px", borderBottom: i < REVIEWS.length - 1 ? "1px solid var(--border-subtle)" : "0", display: "flex", alignItems: "center", gap: 12 }}>
                <Avatar name={r.name} size={32} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 500 }}>{r.name}</div>
                  <div style={{ fontSize: 12, color: "var(--fg-3)" }}>{r.title} · <span className="mono">{r.hours}</span></div>
                </div>
                <Button variant="secondary" size="sm">Review</Button>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <Card>
        <CardHeader title="Members" action={
          <div style={{ display: "flex", gap: 8 }}>
            <button className="icon-btn"><Icon name="filter" size={14} /></button>
            <Button variant="ghost" size="sm" icon="user-plus">Invite</Button>
          </div>
        } />
        <table className="table">
          <thead>
            <tr>
              <th>Member</th>
              <th>Role</th>
              <th>Today</th>
              <th>This week</th>
              <th>On-time</th>
              <th>Status</th>
              <th style={{ width: 32 }}></th>
            </tr>
          </thead>
          <tbody>
            {MEMBERS.map((m, i) => (
              <tr key={i}>
                <td>
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <Avatar name={m.name} size={28} presence={m.online ? "online" : null} />
                    <div>
                      <div style={{ fontWeight: 500 }}>{m.name}</div>
                      <div style={{ fontSize: 11, color: "var(--fg-3)" }}>{m.email}</div>
                    </div>
                  </div>
                </td>
                <td style={{ fontSize: 12, color: "var(--fg-2)" }}>{m.role}</td>
                <td className="mono">{m.today}</td>
                <td>
                  <div className="mono" style={{ fontSize: 13 }}>{m.week}</div>
                  <div style={{ height: 4, background: "var(--slate-100)", borderRadius: 2, marginTop: 4, overflow: "hidden", width: 100 }}>
                    <div style={{ width: `${m.weekPct}%`, height: "100%", background: m.weekPct >= 90 ? "var(--green-500)" : m.weekPct >= 70 ? "var(--chart-1)" : "var(--amber-500)" }} />
                  </div>
                </td>
                <td className="mono" style={{ color: m.ontime >= 90 ? "var(--green-700)" : "var(--fg-1)" }}>{m.ontime}%</td>
                <td><Badge variant={m.statusVar}>{m.status}</Badge></td>
                <td><button className="icon-btn"><Icon name="more-horizontal" size={14} /></button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </>
  );
}

const REVIEWS = [
  { name: "Jordan Kim",   title: "May 24 — daily",       hours: "8h 10m" },
  { name: "Ana Núñez",    title: "May 24 — daily",       hours: "5h 30m" },
  { name: "Lin Chen",     title: "May 23 — daily",       hours: "7h 00m" },
];

const MEMBERS = [
  { name: "Priya Ramanujan", email: "priya@worktrack.app", role: "Senior Engineer", today: "4h 45m", week: "32h 15m", weekPct: 95, ontime: 96, status: "in review",   statusVar: "info",    online: true },
  { name: "Jordan Kim",      email: "jkim@worktrack.app",  role: "Engineer",        today: "8h 10m", week: "38h 20m", weekPct: 100, ontime: 100, status: "submitted",  statusVar: "success", online: true },
  { name: "Ana Núñez",       email: "ana@worktrack.app",   role: "Engineer",        today: "5h 30m", week: "31h 50m", weekPct: 93, ontime: 92, status: "submitted",    statusVar: "success", online: true },
  { name: "Marco Velez",     email: "marco@worktrack.app", role: "Manager",         today: "—",      week: "—",       weekPct: 0,  ontime: 88, status: "n/a",          statusVar: "neutral", online: true },
  { name: "Lin Chen",        email: "lin@worktrack.app",   role: "Engineer",        today: "—",      week: "22h 40m", weekPct: 68, ontime: 76, status: "blocked",      statusVar: "danger",  online: false },
  { name: "Hassan Al-Awar",  email: "hassan@worktrack.app",role: "Senior Engineer", today: "6h 50m", week: "33h 30m", weekPct: 96, ontime: 90, status: "submitted",   statusVar: "success", online: false },
  { name: "Riya Shah",       email: "riya@worktrack.app",  role: "Engineer",        today: "—",      week: "12h 00m", weekPct: 36, ontime: 50, status: "on leave",     statusVar: "neutral", online: false },
];

function TeamBars() {
  const data = [
    { n: "Jordan",  v: 38 }, { n: "Hassan",  v: 33 }, { n: "Priya",   v: 32 },
    { n: "Ana",     v: 31 }, { n: "Lin",     v: 22 }, { n: "Riya",    v: 12 },
  ];
  const max = 40;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {data.map((d, i) => (
        <div key={i} style={{ display: "grid", gridTemplateColumns: "76px 1fr 56px", gap: 10, alignItems: "center" }}>
          <span style={{ fontSize: 12, color: "var(--fg-2)" }}>{d.n}</span>
          <div style={{ height: 10, background: "var(--slate-100)", borderRadius: 4, overflow: "hidden" }}>
            <div style={{ width: `${(d.v / max) * 100}%`, height: "100%", background: "var(--chart-1)", opacity: 0.9 }} />
          </div>
          <span className="mono" style={{ fontSize: 12, textAlign: "right" }}>{d.v}h</span>
        </div>
      ))}
    </div>
  );
}

window.Team = Team;
