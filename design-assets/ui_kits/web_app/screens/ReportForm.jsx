/* Daily Report Submission — enterprise fields per spec:
   Project · Activity type · Tags / Docs / BOM / Spares / Task counts ·
   Remarks · Queries · Work location · Day status */

function ReportForm({ onNavigate, showToast }) {
  const [dayStatus, setDayStatus]   = useState("Working day");
  const [workLocation, setWorkLoc]  = useState("Office — HQ");
  const [shift, setShift]           = useState("General · 09:00 – 18:00");
  const [project, setProject]       = useState("WorkTrack Web · sprint 14");
  const [activity, setActivity]     = useState("Design review");

  // Count fields per spec
  const [counts, setCounts] = useState({ tags: 12, docs: 4, bom: 2, spares: 0, tasksDone: 6, tasksOpen: 3 });
  const updateCount = (k, v) => setCounts({ ...counts, [k]: v });

  const [remarks, setRemarks] = useState("Reviewed token migration with brand team. Closed 6 review-queue items and shipped bulk approve (PR #1284). Blocked on design tokens for the new analytics dashboard — Lin owns.");
  const [queries, setQueries] = useState("Should the BOM upload accept .xlsx in addition to .csv? Finance wants both. Tagging @marco for visibility.");

  const dayStatusOptions = ["Working day", "Half day", "Leave (CL)", "Leave (SL)", "Work from home", "Comp off", "Holiday"];
  const locationOptions  = ["Office — HQ", "Office — Annex", "Client site", "Work from home", "Field"];
  const activityOptions  = ["Development", "Design review", "Code review", "Documentation", "Meetings", "Planning", "Support / on-call", "Training"];
  const projectOptions   = ["WorkTrack Web · sprint 14", "Mobile · Reporting API", "Onboarding redesign", "Q3 planning", "Customer support — ACME"];

  const isLeave = dayStatus.startsWith("Leave") || dayStatus === "Holiday";

  return (
    <>
      <PageHeader
        title="New daily report"
        sub="Friday, May 24, 2026 · auto-saved 12s ago"
        actions={
          <>
            <Button variant="ghost" onClick={() => onNavigate("dashboard")}>Discard</Button>
            <Button variant="secondary" icon="bookmark">Save draft</Button>
            <Button variant="primary" icon="send" onClick={() => { showToast?.({ title: "Report submitted", desc: "Sent to Marco Velez for review.", variant: "success" }); onNavigate("dashboard"); }}>Submit report</Button>
          </>
        }
      />

      <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) 320px", gap: 16, alignItems: "start" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>

          {/* Header band — day status + location + shift */}
          <Card>
            <CardHeader title="Day details" meta="metadata for this report" />
            <CardBody>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 14 }}>
                <Field label="Day status">
                  <PillSelect value={dayStatus} options={dayStatusOptions} onChange={setDayStatus} />
                </Field>
                <Field label="Work location">
                  <PillSelect value={workLocation} options={locationOptions} onChange={setWorkLoc} />
                </Field>
                <Field label="Shift">
                  <PillSelect value={shift} options={["General · 09:00 – 18:00", "Early · 07:00 – 16:00", "Late · 12:00 – 21:00", "Night · 21:00 – 06:00"]} onChange={setShift} />
                </Field>
              </div>
            </CardBody>
          </Card>

          {isLeave ? (
            <Card>
              <CardBody style={{ display: "flex", alignItems: "center", gap: 12, padding: "18px 20px" }}>
                <div style={{ width: 36, height: 36, borderRadius: 8, background: "var(--amber-50)", display: "flex", alignItems: "center", justifyContent: "center" }}>
                  <Icon name="palmtree" size={18} style={{ color: "var(--amber-700)" }} />
                </div>
                <div>
                  <div style={{ fontWeight: 600 }}>{dayStatus} — no work fields required</div>
                  <div style={{ fontSize: 13, color: "var(--fg-3)" }}>Your leave is reflected in attendance. Use Remarks below if you want to note context.</div>
                </div>
                <Button variant="secondary" size="sm" style={{ marginLeft: "auto" }} onClick={() => onNavigate("attendance")}>Go to attendance</Button>
              </CardBody>
            </Card>
          ) : (
            <>
              {/* Work line — project + activity */}
              <Card>
                <CardHeader title="Work" meta="what you worked on today" />
                <CardBody>
                  <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: 14, marginBottom: 14 }}>
                    <Field label="Project">
                      <PillSelect value={project} options={projectOptions} onChange={setProject} />
                    </Field>
                    <Field label="Activity type">
                      <PillSelect value={activity} options={activityOptions} onChange={setActivity} />
                    </Field>
                  </div>

                  {/* Counts grid — six fields */}
                  <div className="field-label" style={{ marginBottom: 10 }}>Counts</div>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: 10 }}>
                    <CountField label="Tags"        icon="hash"            value={counts.tags}      onChange={(v) => updateCount("tags", v)} />
                    <CountField label="Docs"        icon="file-text"       value={counts.docs}      onChange={(v) => updateCount("docs", v)} />
                    <CountField label="BOM"         icon="package"         value={counts.bom}       onChange={(v) => updateCount("bom", v)} />
                    <CountField label="Spares"      icon="wrench"          value={counts.spares}    onChange={(v) => updateCount("spares", v)} />
                    <CountField label="Tasks done"  icon="check-circle-2"  value={counts.tasksDone} onChange={(v) => updateCount("tasksDone", v)} accent="success" />
                    <CountField label="Tasks open"  icon="circle-dashed"   value={counts.tasksOpen} onChange={(v) => updateCount("tasksOpen", v)} accent="warning" />
                  </div>
                  <div className="field-help" style={{ marginTop: 8 }}>Counts roll up into project KPIs and team analytics.</div>
                </CardBody>
              </Card>

              {/* Notes */}
              <Card>
                <CardHeader title="Remarks" meta="visible to your manager" />
                <CardBody>
                  <Textarea value={remarks} onChange={(e) => setRemarks(e.target.value)} placeholder="What did you work on? Decisions, PRs, tickets." style={{ minHeight: 90 }} />
                </CardBody>
              </Card>

              <Card>
                <CardHeader title="Queries / blockers" meta="@mention to escalate" />
                <CardBody>
                  <Textarea value={queries} onChange={(e) => setQueries(e.target.value)} placeholder="Anything blocking you? Questions for management?" style={{ minHeight: 70 }} />
                </CardBody>
              </Card>
            </>
          )}
        </div>

        {/* Sidecar */}
        <div style={{ display: "flex", flexDirection: "column", gap: 16, position: "sticky", top: 72 }}>
          <Card>
            <CardHeader title="Today's totals" />
            <CardBody>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                <span style={{ fontSize: 12, color: "var(--fg-3)" }}>Tasks closed</span>
                <span className="mono" style={{ fontSize: 22, fontWeight: 600 }}>{counts.tasksDone}</span>
              </div>
              <div style={{ height: 1, background: "var(--border-subtle)", margin: "12px 0" }} />
              <SidecarRow icon="hash"           label="Tags"   value={counts.tags} />
              <SidecarRow icon="file-text"      label="Docs"   value={counts.docs} />
              <SidecarRow icon="package"        label="BOM"    value={counts.bom} />
              <SidecarRow icon="wrench"         label="Spares" value={counts.spares} />
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Submitted by team" meta="3 of 8" />
            <div>
              {[
                { name: "Jordan Kim",  time: "4:18 PM", status: "done", v: "success" },
                { name: "Ana Núñez",   time: "3:50 PM", status: "done", v: "success" },
                { name: "Hassan Al-Awar", time: "2:30 PM", status: "done", v: "success" },
                { name: "Lin Chen",    time: "pending", status: "open", v: "warning" },
                { name: "Riya Shah",   time: "on leave", status: "leave", v: "neutral" },
              ].map((p, i, a) => (
                <div key={i} style={{ padding: "10px 16px", display: "flex", alignItems: "center", gap: 10, borderTop: i > 0 ? "1px solid var(--border-subtle)" : "0" }}>
                  <Avatar name={p.name} size={26} />
                  <div style={{ fontSize: 13, flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 500 }}>{p.name}</div>
                    <div style={{ color: "var(--fg-3)", fontSize: 11 }}>{p.time}</div>
                  </div>
                  <Badge variant={p.v} dot={false}>{p.status}</Badge>
                </div>
              ))}
            </div>
          </Card>

          <div style={{ fontSize: 11, color: "var(--fg-3)", padding: "0 4px", display: "flex", alignItems: "flex-start", gap: 6 }}>
            <Icon name="info" size={11} style={{ marginTop: 2 }} />
            <span>Reports lock at midnight. You can edit submitted reports for 24 hours.</span>
          </div>
        </div>
      </div>
    </>
  );
}

function CountField({ label, icon, value, onChange, accent }) {
  const tint = accent === "success" ? "var(--green-700)" : accent === "warning" ? "var(--amber-700)" : "var(--fg-1)";
  return (
    <div style={{
      background: "#fff",
      border: "1px solid var(--border)",
      borderRadius: "var(--radius-md)",
      padding: "10px 12px",
      display: "flex", flexDirection: "column", gap: 6,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: "var(--fg-3)", letterSpacing: "0.04em", textTransform: "uppercase", fontWeight: 600 }}>
        <Icon name={icon} size={11} /> {label}
      </div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 4 }}>
        <input
          type="number" min="0" value={value}
          onChange={(e) => onChange(parseInt(e.target.value || "0", 10))}
          style={{ width: "100%", border: 0, padding: 0, fontFamily: "var(--font-sans)", fontVariantNumeric: "tabular-nums", fontSize: 22, fontWeight: 600, color: tint, background: "transparent", outline: "none" }}
        />
        <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
          <button onClick={() => onChange(value + 1)} style={{ background: "var(--slate-50)", border: "1px solid var(--border)", borderRadius: 3, width: 18, height: 12, fontSize: 9, color: "var(--fg-2)", cursor: "pointer" }}>▲</button>
          <button onClick={() => onChange(Math.max(0, value - 1))} style={{ background: "var(--slate-50)", border: "1px solid var(--border)", borderRadius: 3, width: 18, height: 12, fontSize: 9, color: "var(--fg-2)", cursor: "pointer" }}>▼</button>
        </div>
      </div>
    </div>
  );
}

function SidecarRow({ icon, label, value }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "6px 0", fontSize: 13 }}>
      <Icon name={icon} size={13} style={{ color: "var(--fg-3)" }} />
      <span style={{ color: "var(--fg-2)" }}>{label}</span>
      <span className="mono" style={{ marginLeft: "auto", fontWeight: 500 }}>{value}</span>
    </div>
  );
}

function PillSelect({ value, options, onChange }) {
  const [open, setOpen] = useState(false);
  return (
    <div style={{ position: "relative" }}>
      <div className="select-trigger" onClick={() => setOpen(!open)} tabIndex={0}>
        <span>{value}</span>
        <Icon name="chevron-down" size={14} style={{ color: "var(--fg-3)" }} />
      </div>
      {open && (
        <>
          <div style={{ position: "fixed", inset: 0, zIndex: 9 }} onClick={() => setOpen(false)} />
          <div style={{ position: "absolute", top: "100%", left: 0, right: 0, marginTop: 4, background: "#fff", border: "1px solid var(--border)", borderRadius: "var(--radius-md)", boxShadow: "var(--shadow-md)", padding: 4, zIndex: 10, maxHeight: 280, overflow: "auto" }}>
            {options.map((opt) => (
              <div
                key={opt}
                onClick={() => { onChange(opt); setOpen(false); }}
                style={{ padding: "6px 10px", fontSize: 13, borderRadius: 4, cursor: "pointer", display: "flex", alignItems: "center", gap: 8, background: opt === value ? "var(--bg-subtle)" : "transparent" }}
              >
                {opt === value && <Icon name="check" size={13} style={{ color: "var(--brand)" }} />}
                <span style={{ marginLeft: opt === value ? 0 : 21 }}>{opt}</span>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

window.ReportForm = ReportForm;
