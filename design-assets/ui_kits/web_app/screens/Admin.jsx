/* Admin panel — people & projects management */

function Admin() {
  const [tab, setTab] = useState("people");
  const [inviteOpen, setInviteOpen] = useState(false);
  return (
    <>
      <PageHeader
        title="Admin"
        sub="Manage workspace members, projects, roles, and SSO."
        actions={
          tab === "people"
            ? <Button variant="primary" icon="user-plus" onClick={() => setInviteOpen(true)}>Invite people</Button>
            : <Button variant="primary" icon="plus">New project</Button>
        }
      />

      <Tabs
        value={tab} onChange={setTab}
        items={[
          { value: "people",      label: "People",      count: 47 },
          { value: "projects",    label: "Projects",    count: 12 },
          { value: "roles",       label: "Roles" },
          { value: "leave",       label: "Leave approvals", count: 4 },
          { value: "corrections", label: "Attendance corrections", count: 2 },
          { value: "audit",       label: "Audit log" },
          { value: "sso",         label: "SSO" },
        ]}
      />

      <div style={{ marginTop: 16 }}>
        {tab === "people"      && <PeopleTab />}
        {tab === "projects"    && <ProjectsTab />}
        {tab === "roles"       && <RolesTab />}
        {tab === "leave"       && <LeaveApprovalsTab />}
        {tab === "corrections" && <AttendanceCorrectionsTab />}
        {tab === "audit"       && <AuditLogTab />}
        {tab === "sso"         && <SsoTab />}
      </div>

      <Modal
        open={inviteOpen} onClose={() => setInviteOpen(false)}
        title="Invite people"
        description="Invitees will receive an email with a link to join your workspace."
        footer={
          <>
            <Button variant="ghost" onClick={() => setInviteOpen(false)}>Cancel</Button>
            <Button variant="primary" onClick={() => setInviteOpen(false)}>Send invites</Button>
          </>
        }
      >
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <Field label="Work emails" help="Separate with commas. Up to 20 at once.">
            <Textarea placeholder="ana@company.com, lin@company.com" />
          </Field>
          <Field label="Default role">
            <Select value="Employee" />
          </Field>
          <Field label="Team">
            <Select value="Platform" />
          </Field>
        </div>
      </Modal>
    </>
  );
}

function PeopleTab() {
  return (
    <Card style={{ padding: 0 }}>
      <div style={{ padding: 12, display: "flex", gap: 8, alignItems: "center", borderBottom: "1px solid var(--border-subtle)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "0 12px", height: 30, background: "var(--bg-subtle)", borderRadius: "var(--radius-sm)", flex: 1, fontSize: 13, color: "var(--fg-3)" }}>
          <Icon name="search" size={14} /> Search 47 members…
        </div>
        <button className="btn btn-secondary btn-sm"><Icon name="filter" size={13} /> Filter</button>
      </div>
      <table className="table">
        <thead>
          <tr><th>Member</th><th>Role</th><th>Team</th><th>Joined</th><th>Status</th><th style={{ width: 32 }}></th></tr>
        </thead>
        <tbody>
          {PEOPLE.map((p, i) => (
            <tr key={i}>
              <td>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <Avatar name={p.name} size={28} />
                  <div>
                    <div style={{ fontWeight: 500 }}>{p.name}</div>
                    <div style={{ fontSize: 11, color: "var(--fg-3)" }}>{p.email}</div>
                  </div>
                </div>
              </td>
              <td><span style={{ fontSize: 12, fontWeight: 500, color: p.role === "Admin" ? "var(--blue-700)" : "var(--fg-1)" }}>{p.role}</span></td>
              <td style={{ color: "var(--fg-2)" }}>{p.team}</td>
              <td className="mono" style={{ color: "var(--fg-2)" }}>{p.joined}</td>
              <td><Badge variant={p.statusVar}>{p.status}</Badge></td>
              <td><button className="icon-btn"><Icon name="more-horizontal" size={14} /></button></td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

function ProjectsTab() {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 12 }}>
      {PROJECTS_ADMIN.map((p, i) => (
        <Card key={i}>
          <CardBody>
            <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 12 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span style={{ width: 8, height: 8, borderRadius: 2, background: p.color }} />
                <div>
                  <div style={{ fontWeight: 600 }}>{p.name}</div>
                  <div style={{ fontSize: 12, color: "var(--fg-3)" }}>{p.code}</div>
                </div>
              </div>
              <Badge variant={p.statusVar}>{p.status}</Badge>
            </div>
            <div style={{ display: "flex", gap: 24, fontSize: 12 }}>
              <div><div style={{ color: "var(--fg-3)" }}>Members</div><div style={{ fontWeight: 500, marginTop: 2 }}>{p.members}</div></div>
              <div><div style={{ color: "var(--fg-3)" }}>Hours this month</div><div className="mono" style={{ fontWeight: 500, marginTop: 2 }}>{p.hours}</div></div>
              <div style={{ marginLeft: "auto" }}><AvatarStack names={p.team} size={22} /></div>
            </div>
          </CardBody>
        </Card>
      ))}
    </div>
  );
}

function RolesTab() {
  const roles = [
    { name: "Admin",    desc: "Full access. Manage members, projects, billing, SSO.", count: 3 },
    { name: "Manager",  desc: "Review team reports, manage projects they own.",        count: 6 },
    { name: "Employee", desc: "Submit and edit own reports.",                          count: 36 },
    { name: "Viewer",   desc: "Read-only access to project pages.",                    count: 2 },
  ];
  return (
    <Card style={{ padding: 0 }}>
      {roles.map((r, i) => (
        <div key={i} style={{ display: "flex", alignItems: "center", padding: "16px 20px", borderBottom: i < roles.length - 1 ? "1px solid var(--border-subtle)" : "0" }}>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 500 }}>{r.name}</div>
            <div style={{ fontSize: 12, color: "var(--fg-3)", marginTop: 2 }}>{r.desc}</div>
          </div>
          <span className="mono" style={{ fontSize: 12, color: "var(--fg-2)", marginRight: 16 }}>{r.count} members</span>
          <Button variant="ghost" size="sm">Edit</Button>
        </div>
      ))}
    </Card>
  );
}

function LeaveApprovalsTab() {
  const rows = [
    { name: "Ana Núñez",       type: "CL", from: "May 28",     to: "May 28",     days: 1, reason: "Family event",                  applied: "2 days ago",  v: "warning" },
    { name: "Lin Chen",        type: "SL", from: "May 27",     to: "May 28",     days: 2, reason: "Doctor visit + recovery",       applied: "1 day ago",   v: "warning" },
    { name: "Jordan Kim",      type: "EL", from: "Jun 02",     to: "Jun 06",     days: 5, reason: "Annual trip",                   applied: "3 hours ago", v: "warning" },
    { name: "Hassan Al-Awar",  type: "CO", from: "May 30",     to: "May 30",     days: 1, reason: "Comp off for May 1 work",        applied: "Yesterday",   v: "warning" },
  ];
  return (
    <Card style={{ padding: 0 }}>
      <table className="table">
        <thead>
          <tr><th>Employee</th><th>Type</th><th>Dates</th><th>Days</th><th>Reason</th><th>Applied</th><th style={{ width: 180 }}>Action</th></tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              <td>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <Avatar name={r.name} size={26} />
                  <span style={{ fontWeight: 500 }}>{r.name}</span>
                </div>
              </td>
              <td><Badge variant="info" dot={false}>{r.type}</Badge></td>
              <td><div className="mono" style={{ fontSize: 13 }}>{r.from}</div><div className="mono" style={{ fontSize: 11, color: "var(--fg-3)" }}>→ {r.to}</div></td>
              <td className="mono">{r.days}d</td>
              <td style={{ color: "var(--fg-2)", maxWidth: 240, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.reason}</td>
              <td className="mono" style={{ fontSize: 12, color: "var(--fg-3)" }}>{r.applied}</td>
              <td>
                <div style={{ display: "flex", gap: 6 }}>
                  <Button variant="primary" size="sm" icon="check">Approve</Button>
                  <Button variant="ghost" size="sm">Deny</Button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

function AttendanceCorrectionsTab() {
  const rows = [
    { name: "Lin Chen",     date: "May 21", reason: "Forgot to punch out — left at 19:30",            applied: "2 days ago" },
    { name: "Riya Shah",    date: "May 19", reason: "Punch system was down between 09:00 and 09:20",  applied: "Yesterday" },
  ];
  return (
    <Card style={{ padding: 0 }}>
      <table className="table">
        <thead>
          <tr><th>Employee</th><th>Date</th><th>Reason</th><th>Applied</th><th style={{ width: 180 }}>Action</th></tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              <td>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <Avatar name={r.name} size={26} />
                  <span style={{ fontWeight: 500 }}>{r.name}</span>
                </div>
              </td>
              <td className="mono">{r.date}</td>
              <td style={{ color: "var(--fg-2)" }}>{r.reason}</td>
              <td className="mono" style={{ fontSize: 12, color: "var(--fg-3)" }}>{r.applied}</td>
              <td>
                <div style={{ display: "flex", gap: 6 }}>
                  <Button variant="primary" size="sm" icon="check">Approve</Button>
                  <Button variant="ghost" size="sm">Deny</Button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

function AuditLogTab() {
  const events = [
    { time: "4:32 PM",        actor: "Priya Ramanujan",  action: "submitted",      object: "Daily report · May 24",       meta: "from 10.42.18.205" },
    { time: "3:14 PM",        actor: "Marco Velez",      action: "approved",       object: "Leave (CL) · Ana Núñez · May 28", meta: "manager workflow" },
    { time: "2:08 PM",        actor: "system",           action: "auto-locked",    object: "Reports for May 23",          meta: "scheduled · 00:00 IST" },
    { time: "1:46 PM",        actor: "Tomás Ribeiro",    action: "invited",        object: "sam@worktrack.app · Viewer",   meta: "invite expires 7 days" },
    { time: "11:08 AM",       actor: "Marco Velez",      action: "modified role",  object: "Tomás Ribeiro → Manager",     meta: "previously Employee" },
    { time: "Yesterday 4:22 PM", actor: "system",        action: "exported",       object: "Monthly attendance · May",     meta: "PDF · 47 employees" },
    { time: "Yesterday 9:01 AM", actor: "Priya Ramanujan", action: "created",      object: "Project WT-MOB-API",          meta: "duplicated from sprint 13" },
    { time: "May 22, 5:14 PM",actor: "Lin Chen",         action: "requested",      object: "Attendance correction · May 21", meta: null },
  ];
  return (
    <Card style={{ padding: 0 }}>
      <div style={{ padding: 12, display: "flex", gap: 8, alignItems: "center", borderBottom: "1px solid var(--border-subtle)" }}>
        <div className="search-field" style={{ width: 280, height: 30, background: "var(--bg-subtle)", borderRadius: 6, padding: "0 12px", display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: "var(--fg-3)" }}>
          <Icon name="search" size={13} /> Search audit events…
        </div>
        <Button variant="secondary" size="sm" icon="calendar">Date range</Button>
        <Button variant="secondary" size="sm" icon="user">Actor</Button>
        <div style={{ marginLeft: "auto" }}>
          <Button variant="secondary" size="sm" icon="download">Export</Button>
        </div>
      </div>
      <table className="table">
        <thead>
          <tr><th>Time</th><th>Actor</th><th>Action</th><th>Object</th><th>Context</th></tr>
        </thead>
        <tbody>
          {events.map((e, i) => (
            <tr key={i}>
              <td className="mono" style={{ color: "var(--fg-2)", fontSize: 12 }}>{e.time}</td>
              <td>
                {e.actor === "system" ? (
                  <span style={{ display: "inline-flex", alignItems: "center", gap: 8, color: "var(--fg-3)", fontSize: 13 }}>
                    <Icon name="cog" size={13} /> system
                  </span>
                ) : (
                  <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
                    <Avatar name={e.actor} size={20} />
                    <span style={{ fontSize: 13 }}>{e.actor}</span>
                  </span>
                )}
              </td>
              <td><span style={{ color: "var(--fg-2)", fontSize: 13 }}>{e.action}</span></td>
              <td style={{ fontSize: 13, color: "var(--fg-link)" }}>{e.object}</td>
              <td style={{ fontSize: 12, color: "var(--fg-3)" }} className="mono">{e.meta || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

function SsoTab() {
  return (
    <Card>
      <CardBody>
        <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 16 }}>
          <div style={{ width: 36, height: 36, borderRadius: 8, background: "var(--bg-subtle)", display: "flex", alignItems: "center", justifyContent: "center" }}>
            <Icon name="shield-check" size={18} />
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 500 }}>SAML SSO</div>
            <div style={{ fontSize: 12, color: "var(--fg-3)" }}>Connected to Okta · acme.okta.com</div>
          </div>
          <Badge variant="success">active</Badge>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <Field label="SSO domain"><Input value="worktrack.app" readOnly /></Field>
          <Field label="ACS URL"><Input className="input mono" value="https://worktrack.app/sso/saml/acs" readOnly /></Field>
        </div>
        <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
          <Button variant="secondary" icon="rotate-cw">Re-sync</Button>
          <Button variant="ghost">View metadata</Button>
        </div>
      </CardBody>
    </Card>
  );
}

function BillingTab() {
  return (
    <Card>
      <CardBody>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
          <div>
            <div style={{ fontSize: 11, color: "var(--fg-3)", letterSpacing: "0.04em", textTransform: "uppercase", fontWeight: 600 }}>Current plan</div>
            <div style={{ fontSize: 22, fontWeight: 600, marginTop: 4 }}>Business</div>
            <div style={{ fontSize: 13, color: "var(--fg-2)", marginTop: 2 }}>47 seats · billed annually</div>
          </div>
          <div style={{ textAlign: "right" }}>
            <div className="mono" style={{ fontSize: 22, fontWeight: 600 }}>$564 / mo</div>
            <div style={{ fontSize: 12, color: "var(--fg-3)" }}>next invoice Jun 1</div>
          </div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <Button variant="secondary">Manage seats</Button>
          <Button variant="ghost">View invoices</Button>
        </div>
      </CardBody>
    </Card>
  );
}

const PEOPLE = [
  { name: "Priya Ramanujan", email: "priya@worktrack.app", role: "Employee",  team: "Platform", joined: "2024-03-12", status: "active", statusVar: "success" },
  { name: "Marco Velez",     email: "marco@worktrack.app", role: "Admin",     team: "Platform", joined: "2023-09-01", status: "active", statusVar: "success" },
  { name: "Jordan Kim",      email: "jkim@worktrack.app",  role: "Employee",  team: "Mobile",   joined: "2024-06-04", status: "active", statusVar: "success" },
  { name: "Ana Núñez",       email: "ana@worktrack.app",   role: "Employee",  team: "Mobile",   joined: "2024-08-19", status: "active", statusVar: "success" },
  { name: "Lin Chen",        email: "lin@worktrack.app",   role: "Employee",  team: "Web",      joined: "2025-01-22", status: "active", statusVar: "success" },
  { name: "Riya Shah",       email: "riya@worktrack.app",  role: "Employee",  team: "Web",      joined: "2025-02-10", status: "on leave", statusVar: "warning" },
  { name: "Sam Patel",       email: "sam@worktrack.app",   role: "Viewer",    team: "Finance",  joined: "2025-04-05", status: "active", statusVar: "success" },
  { name: "Tomás Ribeiro",   email: "tomas@worktrack.app", role: "Manager",   team: "Mobile",   joined: "2024-11-15", status: "invited", statusVar: "info" },
];

const PROJECTS_ADMIN = [
  { name: "WorkTrack Web · sprint 14", code: "WT-WEB-14", color: "var(--chart-1)", status: "active", statusVar: "success", members: 8, hours: "282h", team: ["Priya R", "Marco V", "Lin C", "Hassan A"] },
  { name: "Mobile · Reporting API",   code: "MOB-API",    color: "var(--chart-2)", status: "active", statusVar: "success", members: 5, hours: "144h", team: ["Jordan K", "Ana N", "Tomás R"] },
  { name: "Onboarding redesign",     code: "ONB-RD",     color: "var(--chart-3)", status: "at risk", statusVar: "warning", members: 4, hours: "130h", team: ["Riya S", "Lin C", "Marco V"] },
  { name: "Q3 planning",             code: "Q3-PLAN",    color: "var(--chart-4)", status: "draft",  statusVar: "neutral", members: 3, hours: "42h",  team: ["Marco V", "Sam P"] },
];

window.Admin = Admin;
