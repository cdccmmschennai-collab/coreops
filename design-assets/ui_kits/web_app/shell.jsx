/* WorkTrack — AppShell, Sidebar, TopNav */

function Sidebar({ route, onNavigate, role = "employee" }) {
  const items = [
    { id: "dashboard",    label: "Home",            icon: "home" },
    { id: "report",       label: "Today's report",  icon: "file-text" },
    { id: "history",      label: "My reports",      icon: "clipboard-list", count: 12 },
    { id: "attendance",   label: "Attendance",      icon: "calendar-days" },
    { id: "projects",     label: "Projects",        icon: "folder-kanban" },
    { id: "analytics",    label: "Analytics",       icon: "bar-chart-3" },
    { id: "notifications",label: "Notifications",   icon: "bell", count: 3 },
  ];
  const managerItems = [
    { id: "team",      label: "Team",        icon: "users", count: 3 },
  ];
  const adminItems = [
    { id: "admin",     label: "Admin",       icon: "shield-check" },
  ];
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="mark" style={{ background: "var(--brand-mark)" }}>
          <svg viewBox="0 0 32 32" width="16" height="16">
            <rect x="7"  y="18" width="4" height="8"  rx="1" fill="#fff"/>
            <rect x="14" y="13" width="4" height="13" rx="1" fill="#fff"/>
            <rect x="21" y="8"  width="4" height="18" rx="1" fill="#fff"/>
          </svg>
        </div>
        <span className="name">WorkTrack</span>
        <Icon name="chevron-down" size={14} style={{ marginLeft: "auto", color: "var(--fg-3)" }} />
      </div>

      <div className="nav-section">Workspace</div>
      {items.map((it) => <NavItem key={it.id} {...it} active={route === it.id} onClick={() => onNavigate(it.id)} />)}

      {(role === "manager" || role === "admin") && (
        <>
          <div className="nav-section">Manage</div>
          {managerItems.map((it) => <NavItem key={it.id} {...it} active={route === it.id} onClick={() => onNavigate(it.id)} />)}
          {role === "admin" && adminItems.map((it) => <NavItem key={it.id} {...it} active={route === it.id} onClick={() => onNavigate(it.id)} />)}
        </>
      )}

      <div className="sidebar-footer">
        <Avatar name="Priya Ramanujan" size={26} />
        <div style={{ display: "flex", flexDirection: "column", minWidth: 0, fontSize: 12 }}>
          <span style={{ fontWeight: 500, color: "var(--fg-1)" }}>Priya R.</span>
          <span style={{ color: "var(--fg-3)", fontSize: 11 }}>{role === "admin" ? "Admin" : role === "manager" ? "Manager" : "Employee"}</span>
        </div>
        <button className="icon-btn" style={{ marginLeft: "auto" }} title="Sign out">
          <Icon name="log-out" size={14} />
        </button>
      </div>
    </aside>
  );
}

function NavItem({ icon, label, count, active, onClick }) {
  return (
    <button className={`nav-item${active ? " active" : ""}`} onClick={onClick}>
      <Icon name={icon} size={14} strokeWidth={1.7} />
      <span>{label}</span>
      {count != null && <span className="count">{count}</span>}
    </button>
  );
}

function TopNav({ crumbs = [], onToggleNotifications, onToggleSidebar, isMobile }) {
  return (
    <div className="topnav">
      {isMobile && <button className="icon-btn" onClick={onToggleSidebar} title="Menu"><Icon name="menu" size={18} /></button>}
      <div className="crumbs">
        {crumbs.map((c, i) => (
          <React.Fragment key={i}>
            {i > 0 && <span style={{ color: "var(--fg-4)" }}>/</span>}
            <span className={i === crumbs.length - 1 ? "current" : ""}>{c}</span>
          </React.Fragment>
        ))}
      </div>
      <div className="topnav-spacer" />
      {!isMobile && (
        <div className="search-field">
          <Icon name="search" size={14} />
          <span>Search reports, people…</span>
          <span style={{ marginLeft: "auto", fontFamily: "var(--font-mono)", fontSize: 11, background: "var(--slate-150)", padding: "1px 5px", borderRadius: 3, color: "var(--fg-3)" }}>⌘K</span>
        </div>
      )}
      <button className="icon-btn has-dot" title="Notifications" onClick={onToggleNotifications}><Icon name="bell" size={16} /></button>
      <button className="icon-btn" title="Help"><Icon name="circle-help" size={16} /></button>
      <Avatar name="Priya Ramanujan" size={28} presence="online" style={{ cursor: "pointer" }} />
    </div>
  );
}

function AppShell({ route, onNavigate, role, crumbs, children }) {
  const isMobile = useMediaQuery("(max-width: 860px)");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [notifOpen, setNotifOpen] = useState(false);
  useEffect(() => { setSidebarOpen(false); }, [route]);
  const showSidebar = !isMobile || sidebarOpen;
  return (
    <div className={`app-shell${isMobile ? " mobile" : ""}`} data-screen-label={`WorkTrack — ${route}`}>
      {showSidebar && (
        <>
          {isMobile && <div className="sidebar-scrim" onClick={() => setSidebarOpen(false)} />}
          <Sidebar route={route} onNavigate={(r) => { onNavigate(r); setSidebarOpen(false); }} role={role} />
        </>
      )}
      <main className="app-main">
        <TopNav
          crumbs={crumbs}
          onToggleNotifications={() => setNotifOpen((v) => !v)}
          onToggleSidebar={() => setSidebarOpen((v) => !v)}
          isMobile={isMobile}
        />
        <div className="app-content">{children}</div>
      </main>
      <NotificationDrawer open={notifOpen} onClose={() => setNotifOpen(false)} onNavigate={onNavigate} />
    </div>
  );
}

Object.assign(window, { Sidebar, NavItem, TopNav, AppShell });
