/* Attendance — monthly calendar, leave balances, history, analytics */

function Attendance({ onNavigate }) {
  const [month, setMonth] = useState({ y: 2026, m: 4 }); // May 2026 (0-indexed)
  const [tab, setTab] = useState("calendar");

  return (
    <>
      <PageHeader
        title="Attendance"
        sub="Track your presence, shifts, and leave balances. Corrections can be requested up to 7 days back."
        actions={
          <>
            <Button variant="secondary" icon="download">Export</Button>
            <Button variant="primary" icon="plus">Request leave</Button>
          </>
        }
      />

      <div className="kpi-grid" style={{ marginBottom: 16 }}>
        <Kpi label="Present this month" value="18d" delta={{ dir: "up", text: "92% attendance" }} />
        <Kpi label="WFH" value="3d" />
        <Kpi label="Leave taken" value="1d" />
        <Kpi label="Avg hours / day" value="7h 36m" delta={{ dir: "up", text: "+12m" }} />
      </div>

      <Tabs
        value={tab} onChange={setTab}
        items={[
          { value: "calendar", label: "Calendar" },
          { value: "history",  label: "History", count: 22 },
          { value: "balances", label: "Leave balances" },
          { value: "corrections", label: "Corrections", count: 1 },
        ]}
      />

      <div style={{ marginTop: 16 }}>
        {tab === "calendar"    && <CalendarTab month={month} setMonth={setMonth} />}
        {tab === "history"     && <HistoryTab />}
        {tab === "balances"    && <BalancesTab />}
        {tab === "corrections" && <CorrectionsTab />}
      </div>
    </>
  );
}

const MONTHS = ["January","February","March","April","May","June","July","August","September","October","November","December"];
const DOW = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"];

/* Status palette */
const STATUS = {
  present: { bg: "var(--green-50)",  fg: "var(--green-700)",  dot: "var(--green-500)",  label: "Present" },
  wfh:     { bg: "var(--blue-50)",   fg: "var(--blue-700)",   dot: "var(--blue-500)",   label: "WFH" },
  leave:   { bg: "var(--amber-50)",  fg: "var(--amber-700)",  dot: "var(--amber-500)",  label: "Leave" },
  comp:    { bg: "#F3E8FF",          fg: "#6B21A8",           dot: "#8B5CF6",           label: "Comp off" },
  half:    { bg: "var(--slate-100)", fg: "var(--slate-700)",  dot: "var(--slate-500)",  label: "Half day" },
  weekend: { bg: "var(--slate-50)",  fg: "var(--fg-4)",       dot: "var(--slate-300)",  label: "Weekend" },
  holiday: { bg: "var(--red-50)",    fg: "var(--red-700)",    dot: "var(--red-500)",    label: "Holiday" },
  absent:  { bg: "var(--red-50)",    fg: "var(--red-700)",    dot: "var(--red-500)",    label: "Absent" },
};

// May 2026 attendance — May 1 falls on a Friday
const MAY_2026 = {
  1: "present", 2: "weekend", 3: "weekend", 4: "present", 5: "present", 6: "wfh", 7: "present", 8: "leave",
  9: "weekend", 10: "weekend", 11: "present", 12: "present", 13: "present", 14: "holiday", 15: "comp",
  16: "weekend", 17: "weekend", 18: "present", 19: "wfh", 20: "present", 21: "present", 22: "present",
  23: "weekend", 24: "weekend", 25: "present", 26: "present", 27: "present", 28: "present", 29: "present",
  30: "weekend", 31: "weekend",
};

function CalendarTab({ month, setMonth }) {
  const days = new Date(month.y, month.m + 1, 0).getDate();
  // First-of-month day-of-week (Mon=0..Sun=6)
  const firstDow = (new Date(month.y, month.m, 1).getDay() + 6) % 7;
  const cells = Array.from({ length: firstDow }, () => null).concat(Array.from({ length: days }, (_, i) => i + 1));
  while (cells.length % 7 !== 0) cells.push(null);

  return (
    <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) 320px", gap: 16, alignItems: "start" }}>
      <Card>
        <CardHeader
          title={`${MONTHS[month.m]} ${month.y}`}
          action={
            <div style={{ display: "flex", gap: 4 }}>
              <button className="icon-btn" onClick={() => setMonth({ y: month.m === 0 ? month.y - 1 : month.y, m: (month.m + 11) % 12 })}><Icon name="chevron-left" size={14} /></button>
              <Button variant="ghost" size="sm">Today</Button>
              <button className="icon-btn" onClick={() => setMonth({ y: month.m === 11 ? month.y + 1 : month.y, m: (month.m + 1) % 12 })}><Icon name="chevron-right" size={14} /></button>
            </div>
          }
        />
        <CardBody style={{ padding: 16 }}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 0 }}>
            {DOW.map((d) => (
              <div key={d} style={{ padding: "8px 10px", fontSize: 11, color: "var(--fg-3)", fontWeight: 600, letterSpacing: "0.06em", textTransform: "uppercase" }}>{d}</div>
            ))}
            {cells.map((day, i) => {
              if (day == null) return <div key={i} style={{ minHeight: 86, background: "transparent" }} />;
              const status = MAY_2026[day] || "weekend";
              const s = STATUS[status];
              const isToday = day === 25;
              return (
                <div key={i} style={{
                  minHeight: 86, padding: 8,
                  border: "1px solid var(--border-subtle)",
                  marginLeft: -1, marginTop: -1,
                  background: s.bg, position: "relative",
                  display: "flex", flexDirection: "column",
                }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <span className="mono" style={{ fontSize: 13, fontWeight: isToday ? 700 : 500, color: isToday ? "var(--brand)" : s.fg }}>{day}</span>
                    {isToday && <span style={{ fontSize: 9, color: "var(--brand)", fontWeight: 700, letterSpacing: "0.08em" }}>TODAY</span>}
                  </div>
                  <div style={{ marginTop: "auto", display: "flex", alignItems: "center", gap: 5, fontSize: 11, color: s.fg, fontWeight: 500 }}>
                    <span style={{ width: 6, height: 6, borderRadius: "50%", background: s.dot }} />
                    {s.label}
                  </div>
                  {status === "present" && (day === 18 || day === 25) && (
                    <span style={{ position: "absolute", top: 8, right: 8, fontSize: 10, color: "var(--fg-3)", fontVariantNumeric: "tabular-nums" }}>7h{day === 25 ? "" : ""}</span>
                  )}
                </div>
              );
            })}
          </div>
        </CardBody>
      </Card>

      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        <Card>
          <CardHeader title="Legend" />
          <CardBody style={{ padding: 14 }}>
            {Object.entries(STATUS).map(([k, s]) => (
              <div key={k} style={{ display: "flex", alignItems: "center", gap: 10, padding: "5px 0", fontSize: 13 }}>
                <span style={{ width: 14, height: 14, borderRadius: 4, background: s.bg, border: `1px solid ${s.dot}` }} />
                <span>{s.label}</span>
              </div>
            ))}
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Shift" />
          <CardBody style={{ padding: 14 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
              <Icon name="clock" size={14} style={{ color: "var(--fg-3)" }} />
              <span style={{ fontWeight: 500 }}>General</span>
              <Badge variant="info" dot={false}>active</Badge>
            </div>
            <div className="mono" style={{ fontSize: 14, color: "var(--fg-1)" }}>09:00 – 18:00</div>
            <div style={{ fontSize: 12, color: "var(--fg-3)", marginTop: 4 }}>Asia/Kolkata · 9h day · 1h lunch</div>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Today's punch" />
          <CardBody style={{ padding: 14 }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
              <div style={{ fontSize: 12, color: "var(--fg-3)" }}>IN</div>
              <div className="mono" style={{ fontWeight: 500 }}>09:12 AM</div>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 12 }}>
              <div style={{ fontSize: 12, color: "var(--fg-3)" }}>OUT</div>
              <div className="mono" style={{ color: "var(--fg-3)" }}>—</div>
            </div>
            <Button variant="secondary" size="sm" icon="log-out" style={{ width: "100%" }}>Punch out</Button>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}

function HistoryTab() {
  const rows = [
    { date: "May 23",  day: "Fri", status: "present", in: "09:08", out: "18:14", hours: "9h 06m" },
    { date: "May 22",  day: "Thu", status: "present", in: "08:55", out: "18:32", hours: "9h 37m" },
    { date: "May 21",  day: "Wed", status: "present", in: "09:21", out: "17:50", hours: "8h 29m" },
    { date: "May 20",  day: "Tue", status: "present", in: "09:02", out: "18:15", hours: "9h 13m" },
    { date: "May 19",  day: "Mon", status: "wfh",     in: "—",     out: "—",     hours: "8h 00m" },
    { date: "May 16",  day: "Fri", status: "comp",    in: "—",     out: "—",     hours: "—" },
    { date: "May 15",  day: "Thu", status: "holiday", in: "—",     out: "—",     hours: "—" },
    { date: "May 14",  day: "Wed", status: "present", in: "09:00", out: "18:00", hours: "9h 00m" },
    { date: "May 12",  day: "Mon", status: "present", in: "09:11", out: "17:48", hours: "8h 37m" },
    { date: "May 8",   day: "Thu", status: "leave",   in: "—",     out: "—",     hours: "—" },
  ];
  return (
    <Card style={{ padding: 0 }}>
      <table className="table">
        <thead>
          <tr><th>Date</th><th>Status</th><th>IN</th><th>OUT</th><th>Hours</th><th style={{ width: 32 }}></th></tr>
        </thead>
        <tbody>
          {rows.map((r, i) => {
            const s = STATUS[r.status];
            return (
              <tr key={i}>
                <td><div style={{ fontWeight: 500 }}>{r.date}</div><div style={{ fontSize: 11, color: "var(--fg-3)" }}>{r.day}</div></td>
                <td><span className="badge" style={{ background: s.bg, color: s.fg, borderColor: s.dot, borderStyle: "solid", borderWidth: 1 }}><span className="dot" style={{ background: s.dot }} />{s.label}</span></td>
                <td className="mono">{r.in}</td>
                <td className="mono">{r.out}</td>
                <td className="mono" style={{ fontWeight: 500 }}>{r.hours}</td>
                <td><button className="icon-btn"><Icon name="more-horizontal" size={14} /></button></td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </Card>
  );
}

function BalancesTab() {
  const balances = [
    { type: "Casual leave",     code: "CL", used: 4,  total: 12, color: "var(--chart-1)" },
    { type: "Sick leave",       code: "SL", used: 2,  total: 12, color: "var(--chart-2)" },
    { type: "Earned leave",     code: "EL", used: 5,  total: 24, color: "var(--chart-3)" },
    { type: "Comp off",         code: "CO", used: 1,  total: 3,  color: "var(--chart-4)" },
    { type: "Bereavement",      code: "BL", used: 0,  total: 3,  color: "var(--chart-5)" },
    { type: "Parental",         code: "PL", used: 0,  total: 90, color: "var(--chart-6)" },
  ];
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
      {balances.map((b) => {
        const remain = b.total - b.used;
        const pct = (b.used / b.total) * 100;
        return (
          <Card key={b.code}>
            <CardBody>
              <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 12 }}>
                <div>
                  <div style={{ fontSize: 11, color: "var(--fg-3)", letterSpacing: "0.06em", textTransform: "uppercase", fontWeight: 600 }}>{b.code}</div>
                  <div style={{ fontWeight: 600, fontSize: 14, marginTop: 2 }}>{b.type}</div>
                </div>
                <Button variant="ghost" size="sm">Apply</Button>
              </div>
              <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                <span className="mono" style={{ fontSize: 28, fontWeight: 600 }}>{remain}</span>
                <span style={{ fontSize: 12, color: "var(--fg-3)" }}>days remaining</span>
              </div>
              <div style={{ height: 6, background: "var(--slate-100)", borderRadius: 3, overflow: "hidden", marginTop: 10 }}>
                <div style={{ width: `${pct}%`, height: "100%", background: b.color, opacity: 0.85 }} />
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", marginTop: 6, fontSize: 11, color: "var(--fg-3)" }} className="mono">
                <span>{b.used} used</span>
                <span>{b.total} total</span>
              </div>
            </CardBody>
          </Card>
        );
      })}
    </div>
  );
}

function CorrectionsTab() {
  const rows = [
    { date: "May 21", reason: "Forgot to punch out — left at 19:30", status: "pending review", v: "warning" },
    { date: "May 14", reason: "Holiday marked as absent — Buddha Purnima",  status: "approved",     v: "success" },
    { date: "May 06", reason: "Punch in counted twice (09:00 + 09:04)",    status: "approved",     v: "success" },
  ];
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 12 }}>
        <Button variant="primary" icon="plus" size="sm">Request correction</Button>
      </div>
      <Card style={{ padding: 0 }}>
        <table className="table">
          <thead>
            <tr><th>Date</th><th>Reason</th><th>Submitted</th><th>Status</th><th style={{ width: 32 }}></th></tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                <td><div style={{ fontWeight: 500 }}>{r.date}</div></td>
                <td style={{ color: "var(--fg-2)" }}>{r.reason}</td>
                <td className="mono" style={{ color: "var(--fg-3)", fontSize: 12 }}>{i === 0 ? "2 days ago" : "1 week ago"}</td>
                <td><Badge variant={r.v}>{r.status}</Badge></td>
                <td><button className="icon-btn"><Icon name="more-horizontal" size={14} /></button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

window.Attendance = Attendance;
