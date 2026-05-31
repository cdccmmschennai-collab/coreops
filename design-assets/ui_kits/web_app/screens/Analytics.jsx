/* Analytics — charts: hours by category, project burn, team load */

function Analytics() {
  const [range, setRange] = useState("month");
  return (
    <>
      <PageHeader
        title="Analytics"
        sub="Aggregated across all teams. Updated 5 min ago."
        actions={
          <>
            <Segmented value={range} onChange={setRange} items={[
              { value: "week", label: "Week" }, { value: "month", label: "Month" }, { value: "quarter", label: "Quarter" },
            ]} />
            <Button variant="secondary" icon="download">Export</Button>
          </>
        }
      />

      <div className="kpi-grid" style={{ marginBottom: 16 }}>
        <Kpi label="Reports submitted" value="412" delta={{ dir: "up", text: "+8% vs last" }} />
        <Kpi label="Hours logged" value="3,184h" delta={{ dir: "up", text: "+2%" }} />
        <Kpi label="On-time rate" value="91%" delta={{ dir: "up", text: "+3%" }} />
        <Kpi label="Avg review time" value="4.2h" delta={{ dir: "down", text: "−0.8h" }} />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1.6fr) minmax(0, 1fr)", gap: 16, marginBottom: 16 }}>
        <Card>
          <CardHeader title="Hours by category" meta="May · stacked"
            action={<Legend items={[
              { c: "var(--chart-1)", l: "Development" },
              { c: "var(--chart-2)", l: "Reviews" },
              { c: "var(--chart-3)", l: "Meetings" },
              { c: "var(--chart-4)", l: "Planning" },
            ]} />}
          />
          <CardBody><StackedBars /></CardBody>
        </Card>

        <Card>
          <CardHeader title="Hours by category — total" meta="this month" />
          <CardBody><Donut /></CardBody>
        </Card>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1fr)", gap: 16, marginBottom: 16 }}>
        <Card>
          <CardHeader title="Project burn" meta="hours allocated vs logged" />
          <CardBody>
            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              {BURN.map((p, i) => <BurnRow key={i} {...p} />)}
            </div>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="On-time submissions" meta="trailing 12 weeks" />
          <CardBody><LineChart /></CardBody>
        </Card>
      </div>

      <Card>
        <CardHeader title="Workload heatmap" meta="hours per person · last 8 weeks"
          action={<div style={{ display: "flex", gap: 12, fontSize: 11, color: "var(--fg-2)", alignItems: "center" }}>
            <span>0h</span>
            <div style={{ display: "flex", gap: 2 }}>
              {[0.08, 0.2, 0.4, 0.6, 0.85].map((a, i) => <span key={i} style={{ width: 14, height: 10, background: "var(--chart-1)", opacity: a, borderRadius: 2 }} />)}
            </div>
            <span>10h+</span>
          </div>}
        />
        <CardBody><Heatmap /></CardBody>
      </Card>
    </>
  );
}

function Legend({ items }) {
  return (
    <div style={{ display: "flex", gap: 12, fontSize: 11, color: "var(--fg-2)" }}>
      {items.map((it, i) => (
        <span key={i} style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
          <span style={{ width: 8, height: 8, background: it.c, borderRadius: 2 }} /> {it.l}
        </span>
      ))}
    </div>
  );
}

function StackedBars() {
  // 30 days of data
  const data = Array.from({ length: 30 }, (_, i) => {
    const seed = (i * 7) % 11;
    const dev = 80 + ((seed * 5) % 40);
    const rev = 30 + ((seed * 3) % 20);
    const mtg = 15 + ((seed * 2) % 18);
    const plan = (i % 5 === 0) ? 20 : 5 + (seed % 8);
    return { dev, rev, mtg, plan };
  });
  const max = 200;
  const w = 660;
  const bw = (w - 40) / data.length - 1;
  return (
    <svg viewBox={`0 0 ${w} 200`} width="100%" style={{ display: "block" }}>
      <g stroke="var(--border-subtle)" strokeDasharray="2 3" fill="none">
        {[20, 60, 100, 140, 180].map((y) => <line key={y} x1="36" y1={y} x2={w - 4} y2={y} />)}
      </g>
      <g fontFamily="Geist Mono, monospace" fontSize="9" fill="var(--fg-3)" textAnchor="end">
        <text x="32" y="24">200h</text><text x="32" y="64">150</text><text x="32" y="104">100</text><text x="32" y="144">50</text><text x="32" y="184">0</text>
      </g>
      {data.map((d, i) => {
        const x = 40 + i * (bw + 1);
        const scale = 160 / max;
        const hDev = d.dev * scale, hRev = d.rev * scale, hMtg = d.mtg * scale, hPlan = d.plan * scale;
        const y1 = 180 - hDev;
        const y2 = y1 - hRev;
        const y3 = y2 - hMtg;
        const y4 = y3 - hPlan;
        return (
          <g key={i}>
            <rect x={x} y={y1} width={bw} height={hDev} fill="var(--chart-1)" opacity="0.9" />
            <rect x={x} y={y2} width={bw} height={hRev} fill="var(--chart-2)" opacity="0.9" />
            <rect x={x} y={y3} width={bw} height={hMtg} fill="var(--chart-3)" opacity="0.85" />
            <rect x={x} y={y4} width={bw} height={hPlan} fill="var(--chart-4)" opacity="0.85" />
          </g>
        );
      })}
    </svg>
  );
}

function Donut() {
  const slices = [
    { v: 58, c: "var(--chart-1)", l: "Development" },
    { v: 18, c: "var(--chart-2)", l: "Reviews" },
    { v: 14, c: "var(--chart-3)", l: "Meetings" },
    { v: 10, c: "var(--chart-4)", l: "Planning" },
  ];
  const total = slices.reduce((s, x) => s + x.v, 0);
  let acc = 0;
  const R = 60, C = 75;
  return (
    <div style={{ display: "flex", gap: 18, alignItems: "center" }}>
      <svg width="150" height="150" viewBox="0 0 150 150">
        {slices.map((s, i) => {
          const start = (acc / total) * 2 * Math.PI - Math.PI / 2;
          acc += s.v;
          const end = (acc / total) * 2 * Math.PI - Math.PI / 2;
          const large = end - start > Math.PI ? 1 : 0;
          const x1 = C + R * Math.cos(start), y1 = C + R * Math.sin(start);
          const x2 = C + R * Math.cos(end), y2 = C + R * Math.sin(end);
          return <path key={i} d={`M ${C} ${C} L ${x1} ${y1} A ${R} ${R} 0 ${large} 1 ${x2} ${y2} Z`} fill={s.c} opacity="0.92" />;
        })}
        <circle cx={C} cy={C} r="36" fill="#fff" />
        <text x={C} y={C - 4} textAnchor="middle" fontFamily="Geist Mono, monospace" fontSize="18" fontWeight="600" fill="var(--fg-1)">3.2k</text>
        <text x={C} y={C + 14} textAnchor="middle" fontSize="10" fill="var(--fg-3)">hours</text>
      </svg>
      <div style={{ display: "flex", flexDirection: "column", gap: 8, fontSize: 12, flex: 1 }}>
        {slices.map((s, i) => (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ width: 10, height: 10, background: s.c, borderRadius: 2 }} />
            <span style={{ flex: 1 }}>{s.l}</span>
            <span className="mono" style={{ color: "var(--fg-1)" }}>{s.v}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function BurnRow({ name, alloc, logged, color }) {
  const pct = Math.min(100, Math.round((logged / alloc) * 100));
  const over = logged > alloc;
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 6 }}>
        <span style={{ fontSize: 13, fontWeight: 500 }}>{name}</span>
        <span className="mono" style={{ fontSize: 12, color: over ? "var(--red-700)" : "var(--fg-2)" }}>{logged}h / {alloc}h</span>
      </div>
      <div style={{ height: 8, background: "var(--slate-100)", borderRadius: 4, overflow: "hidden", position: "relative" }}>
        <div style={{ width: `${pct}%`, height: "100%", background: over ? "var(--red-500)" : color, opacity: 0.95 }} />
      </div>
    </div>
  );
}

const BURN = [
  { name: "WorkTrack Web · sprint 14",   alloc: 320, logged: 282, color: "var(--chart-1)" },
  { name: "Mobile · Reporting API",     alloc: 180, logged: 144, color: "var(--chart-2)" },
  { name: "Onboarding redesign",        alloc: 120, logged: 130, color: "var(--chart-3)" },
  { name: "Q3 planning",                alloc: 60,  logged: 42,  color: "var(--chart-4)" },
];

function LineChart() {
  const data = [78, 82, 85, 81, 84, 88, 90, 86, 89, 91, 93, 91];
  const w = 320, h = 130, pad = 12;
  const max = 100, min = 60;
  const pts = data.map((v, i) => {
    const x = pad + (i / (data.length - 1)) * (w - pad * 2);
    const y = pad + (1 - (v - min) / (max - min)) * (h - pad * 2);
    return [x, y];
  });
  const d = pts.map((p, i) => `${i === 0 ? "M" : "L"}${p[0]},${p[1]}`).join(" ");
  const area = `${d} L ${pts[pts.length - 1][0]},${h - pad} L ${pts[0][0]},${h - pad} Z`;
  return (
    <svg viewBox={`0 0 ${w} ${h + 16}`} width="100%" style={{ display: "block" }}>
      <g stroke="var(--border-subtle)" strokeDasharray="2 3" fill="none">
        {[pad, h / 2, h - pad].map((y) => <line key={y} x1={pad} y1={y} x2={w - pad} y2={y} />)}
      </g>
      <path d={area} fill="var(--chart-1)" opacity="0.10" />
      <path d={d} stroke="var(--chart-1)" strokeWidth="2" fill="none" />
      {pts.map((p, i) => <circle key={i} cx={p[0]} cy={p[1]} r={i === pts.length - 1 ? 3 : 0} fill="var(--chart-1)" />)}
      <text x={pts[pts.length - 1][0] + 8} y={pts[pts.length - 1][1] + 4} fontFamily="Geist Mono, monospace" fontSize="11" fill="var(--fg-1)">91%</text>
      <g fontFamily="Geist Mono, monospace" fontSize="9" fill="var(--fg-3)">
        <text x={pad} y={h + 12}>wk 11</text>
        <text x={(w - pad * 2) / 2} y={h + 12} textAnchor="middle">wk 17</text>
        <text x={w - pad} y={h + 12} textAnchor="end">wk 22</text>
      </g>
    </svg>
  );
}

window.Analytics = Analytics;

function Heatmap() {
  const people = ["Priya R.", "Jordan K.", "Ana N.", "Hassan A.", "Lin C.", "Riya S.", "Marco V.", "Tomás R."];
  const weeks = 8;
  // Deterministic pseudo-random hours, slightly weighted by row
  const cell = (r, c) => {
    const v = (Math.sin((r + 1) * 12.9898 + (c + 1) * 78.233) * 43758.5453) % 1;
    const base = Math.abs(v) * 11;
    return Math.round(Math.min(11, base * (r === 5 ? 0.5 : r === 6 ? 0.3 : 1)) * 10) / 10;
  };
  return (
    <div style={{ overflow: "auto" }}>
      <div style={{ display: "grid", gridTemplateColumns: "120px repeat(8, minmax(36px, 1fr))", gap: 4, minWidth: 580 }}>
        <div></div>
        {Array.from({ length: weeks }, (_, c) => (
          <div key={c} className="mono" style={{ textAlign: "center", fontSize: 11, color: "var(--fg-3)" }}>w{15 + c}</div>
        ))}
        {people.map((name, r) => (
          <React.Fragment key={r}>
            <div style={{ fontSize: 12, color: "var(--fg-2)", display: "flex", alignItems: "center", gap: 8, paddingRight: 8 }}>
              <Avatar name={name} size={20} />
              {name}
            </div>
            {Array.from({ length: weeks }, (_, c) => {
              const v = cell(r, c);
              const opacity = v < 0.5 ? 0.06 : v / 11 * 0.95;
              const isLow = v < 2;
              return (
                <div key={c} title={`${name} · w${15 + c} · ${v}h/day`} style={{
                  height: 32,
                  background: isLow && v > 0 ? "var(--amber-100)" : v === 0 ? "var(--slate-100)" : "var(--chart-1)",
                  opacity: v === 0 ? 1 : (isLow ? 0.7 : opacity),
                  borderRadius: 4,
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: 10, color: opacity > 0.5 ? "#fff" : "var(--fg-2)",
                  fontVariantNumeric: "tabular-nums", fontWeight: 500,
                }}>
                  {v >= 1 ? v.toFixed(0) : ""}
                </div>
              );
            })}
          </React.Fragment>
        ))}
      </div>
      <div style={{ display: "flex", gap: 18, marginTop: 14, fontSize: 11, color: "var(--fg-3)" }}>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}><span style={{ width: 10, height: 10, background: "var(--amber-100)", borderRadius: 2 }} /> Under-utilized (&lt;2h/d)</span>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}><span style={{ width: 10, height: 10, background: "var(--chart-1)", borderRadius: 2 }} /> Reported hours</span>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}><span style={{ width: 10, height: 10, background: "var(--slate-100)", borderRadius: 2 }} /> No data</span>
      </div>
    </div>
  );
}
