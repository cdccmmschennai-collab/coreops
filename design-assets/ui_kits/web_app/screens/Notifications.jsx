/* Notification Center — full page view of all notifications */

const NOTIFICATIONS = [
  { id: 1,  type: "report-due",        icon: "clock",          read: false, time: "2 minutes ago",      title: "Daily report due today",                       body: "You haven't submitted Friday, May 24. Reports lock at midnight.",                                  cta: { label: "Submit report", to: "report" } },
  { id: 2,  type: "review-pending",    icon: "eye",            read: false, time: "12 minutes ago",     title: "3 reports waiting on your review",             body: "Jordan, Ana, and Lin are waiting for your review on the Platform team.",                            cta: { label: "Review queue", to: "team" } },
  { id: 3,  type: "leave-approved",    icon: "check-circle-2", read: false, time: "1 hour ago",         title: "Leave approved · May 28",                      body: "Marco Velez approved your casual leave for Thursday, May 28. 1 CL deducted.",                       cta: { label: "View attendance", to: "attendance" } },
  { id: 4,  type: "attendance-issue",  icon: "alert-triangle", read: true,  time: "3 hours ago",        title: "Attendance correction approved",               body: "Your May 14 correction (marked holiday) was approved. Attendance updated.",                          cta: { label: "View calendar", to: "attendance" } },
  { id: 5,  type: "deadline",          icon: "calendar-clock", read: true,  time: "Yesterday, 5:30 PM", title: "Sprint 14 ends in 3 days",                     body: "WorkTrack Web · sprint 14 closes May 27. 4 stories still open.",                                     cta: { label: "Open project", to: "projects" } },
  { id: 6,  type: "missing-report",    icon: "circle-alert",   read: true,  time: "Yesterday, 11:08 AM", title: "Riya hasn't submitted in 3 days",             body: "As Platform manager, you're seeing this. Last report was Monday, May 19.",                          cta: { label: "Open member", to: "team" } },
  { id: 7,  type: "report-due",        icon: "clock",          read: true,  time: "May 23, 9:00 AM",    title: "Daily report reminder",                        body: "Heads up — report due today by 5 PM.",                                                              cta: null },
  { id: 8,  type: "correction-req",    icon: "user-cog",       read: true,  time: "May 22, 2:14 PM",    title: "Attendance correction request",                body: "Lin Chen requested correction for May 21. Action required.",                                         cta: { label: "Review", to: "admin" } },
];

function NotificationCenter({ onNavigate }) {
  const [tab, setTab] = useState("all");
  const unread = NOTIFICATIONS.filter((n) => !n.read).length;

  const filtered = NOTIFICATIONS.filter((n) => {
    if (tab === "unread") return !n.read;
    if (tab === "reports") return ["report-due", "deadline", "missing-report"].includes(n.type);
    if (tab === "approvals") return ["leave-approved", "attendance-issue", "correction-req"].includes(n.type);
    return true;
  });

  return (
    <>
      <PageHeader
        title="Notifications"
        sub={`${unread} unread · last 7 days · settings`}
        actions={
          <>
            <Button variant="ghost" icon="check-check">Mark all read</Button>
            <Button variant="secondary" icon="settings">Preferences</Button>
          </>
        }
      />

      <Tabs
        value={tab} onChange={setTab}
        items={[
          { value: "all",       label: "All",       count: NOTIFICATIONS.length },
          { value: "unread",    label: "Unread",    count: unread },
          { value: "reports",   label: "Reports" },
          { value: "approvals", label: "Approvals" },
        ]}
      />

      <Card style={{ marginTop: 16, padding: 0 }}>
        {filtered.map((n, i) => (
          <NotificationRow key={n.id} n={n} last={i === filtered.length - 1} onNavigate={onNavigate} />
        ))}
        {filtered.length === 0 && (
          <EmptyState icon="bell-off" title="No notifications here" description="When something needs your attention, it'll show up here." />
        )}
      </Card>
    </>
  );
}

function NotificationRow({ n, last, onNavigate }) {
  return (
    <div style={{
      display: "flex", gap: 14, padding: "16px 20px",
      borderBottom: last ? "0" : "1px solid var(--border-subtle)",
      background: n.read ? "transparent" : "rgba(63, 99, 224, 0.025)",
    }}>
      {/* unread dot */}
      <div style={{ width: 8, paddingTop: 8 }}>
        {!n.read && <span style={{ display: "block", width: 8, height: 8, borderRadius: "50%", background: "var(--brand)" }} />}
      </div>
      {/* icon */}
      <div style={{
        width: 36, height: 36, borderRadius: 8,
        background: iconBg(n.type), color: iconFg(n.type),
        display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
      }}>
        <Icon name={n.icon} size={18} />
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 12 }}>
          <span style={{ fontSize: 14, fontWeight: n.read ? 500 : 600 }}>{n.title}</span>
          <span style={{ marginLeft: "auto", fontSize: 12, color: "var(--fg-3)" }}>{n.time}</span>
        </div>
        <div style={{ fontSize: 13, color: "var(--fg-2)", marginTop: 2 }}>{n.body}</div>
        {n.cta && (
          <div style={{ marginTop: 10 }}>
            <Button variant="secondary" size="sm" onClick={() => onNavigate(n.cta.to)}>{n.cta.label}</Button>
          </div>
        )}
      </div>
      <button className="icon-btn" title="More"><Icon name="more-horizontal" size={14} /></button>
    </div>
  );
}

function iconBg(type) {
  switch (type) {
    case "report-due":       case "deadline":         return "var(--amber-50)";
    case "review-pending":   case "correction-req":   return "var(--blue-50)";
    case "leave-approved":   case "attendance-issue": return "var(--green-50)";
    case "missing-report":                            return "var(--red-50)";
    default:                                          return "var(--slate-100)";
  }
}
function iconFg(type) {
  switch (type) {
    case "report-due":       case "deadline":         return "var(--amber-700)";
    case "review-pending":   case "correction-req":   return "var(--blue-700)";
    case "leave-approved":   case "attendance-issue": return "var(--green-700)";
    case "missing-report":                            return "var(--red-700)";
    default:                                          return "var(--slate-700)";
  }
}

/* ---------- Drawer used from the top nav ---------- */
function NotificationDrawer({ open, onClose, onNavigate }) {
  if (!open) return null;
  const recent = NOTIFICATIONS.slice(0, 6);
  return (
    <>
      <div style={{ position: "fixed", inset: 0, zIndex: 60 }} onClick={onClose} />
      <div style={{
        position: "fixed", top: 60, right: 16, zIndex: 70,
        width: 380, maxHeight: "calc(100vh - 80px)",
        background: "#fff",
        border: "1px solid var(--border)",
        borderRadius: "var(--radius-xl)",
        boxShadow: "var(--shadow-lg)",
        overflow: "hidden",
        display: "flex", flexDirection: "column",
        animation: "drawerIn 200ms var(--ease-out)",
      }}>
        <div style={{ padding: "14px 16px", borderBottom: "1px solid var(--border-subtle)", display: "flex", alignItems: "center" }}>
          <div style={{ fontSize: 14, fontWeight: 600 }}>Notifications</div>
          <Badge variant="info" dot={false}>{recent.filter((n) => !n.read).length} new</Badge>
          <Button variant="ghost" size="sm" style={{ marginLeft: "auto" }}>Mark all read</Button>
        </div>
        <div style={{ overflow: "auto", flex: 1 }}>
          {recent.map((n, i) => (
            <div key={n.id} onClick={() => { onClose(); n.cta && onNavigate(n.cta.to); }} style={{ display: "flex", gap: 10, padding: "12px 16px", cursor: "pointer", borderBottom: i < recent.length - 1 ? "1px solid var(--border-subtle)" : 0, background: n.read ? "transparent" : "rgba(63, 99, 224, 0.025)" }}>
              {!n.read && <span style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--brand)", marginTop: 6, flexShrink: 0 }} />}
              {n.read && <span style={{ width: 8, flexShrink: 0 }} />}
              <div style={{ width: 28, height: 28, borderRadius: 6, background: iconBg(n.type), color: iconFg(n.type), display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                <Icon name={n.icon} size={14} />
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 13, fontWeight: n.read ? 500 : 600 }}>{n.title}</div>
                <div style={{ fontSize: 12, color: "var(--fg-3)", marginTop: 2, overflow: "hidden", textOverflow: "ellipsis", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical" }}>{n.body}</div>
                <div style={{ fontSize: 11, color: "var(--fg-4)", marginTop: 4 }}>{n.time}</div>
              </div>
            </div>
          ))}
        </div>
        <div style={{ padding: 12, borderTop: "1px solid var(--border-subtle)", background: "var(--bg-surface-muted)", textAlign: "center" }}>
          <button className="btn btn-link" onClick={() => { onClose(); onNavigate("notifications"); }}>View all →</button>
        </div>
      </div>
      <style>{`@keyframes drawerIn { from { opacity: 0; transform: translateY(-4px); } to { opacity: 1; transform: translateY(0); } }`}</style>
    </>
  );
}

Object.assign(window, { NotificationCenter, NotificationDrawer });
