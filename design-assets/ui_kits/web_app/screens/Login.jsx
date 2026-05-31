/* Login — split layout: form left, marketing panel right */

function Login({ onSignIn }) {
  const [email, setEmail] = useState("priya@cadence.work");
  const [password, setPassword] = useState("••••••••••");
  return (
    <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) 1fr", minHeight: "100vh", background: "#fff" }} data-screen-label="Login">
      {/* form */}
      <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", padding: "48px 80px", maxWidth: 520, margin: "0 auto", width: "100%" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 48 }}>
          <svg viewBox="0 0 32 32" width="36" height="36">
            <rect width="32" height="32" rx="7" fill="var(--brand-mark)" />
            <rect x="7"  y="18" width="4" height="8"  rx="1" fill="#fff"/>
            <rect x="14" y="13" width="4" height="13" rx="1" fill="#fff"/>
            <rect x="21" y="8"  width="4" height="18" rx="1" fill="#fff"/>
          </svg>
          <div>
            <div style={{ fontSize: 20, fontWeight: 700, letterSpacing: "-0.02em", lineHeight: 1.1 }}>WorkTrack</div>
            <div style={{ fontSize: 11, color: "var(--fg-2)", marginTop: 2 }}>Employee Work Reporting System</div>
          </div>
        </div>
        <h1 className="t-h2" style={{ margin: 0 }}>{mode === "signin" ? "Sign in to your workspace" : mode === "forgot" ? "Reset your password" : "Check your email"}</h1>
        <p style={{ margin: "8px 0 32px", color: "var(--fg-2)", fontSize: 14 }}>
          {mode === "signin" && "Submit daily reports, track your projects, and review your team."}
          {mode === "forgot" && "Enter your work email and we'll send you a reset link."}
          {mode === "sent"   && "We sent a reset link to " + email + ". The link expires in 30 minutes."}
        </p>

        {mode === "signin" && (
          <>
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              <Button variant="secondary" size="lg" icon="key-round">Continue with Single Sign-On</Button>
              <Button variant="secondary" size="lg" icon="github">Continue with Google Workspace</Button>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: 14, margin: "28px 0 24px", color: "var(--fg-3)", fontSize: 12 }}>
              <div style={{ flex: 1, height: 1, background: "var(--border-subtle)" }} />
              <span>or with email</span>
              <div style={{ flex: 1, height: 1, background: "var(--border-subtle)" }} />
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <Field label="Work email">
                <Input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" />
              </Field>
              <Field label="Password">
                <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
              </Field>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 12, color: "var(--fg-2)" }}>
                <label style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer" }}>
                  <input type="checkbox" defaultChecked style={{ accentColor: "var(--brand)" }} />
                  Keep me signed in
                </label>
                <a href="#" onClick={(e) => { e.preventDefault(); setMode("forgot"); }}>Forgot password?</a>
              </div>
              <Button variant="primary" size="lg" onClick={onSignIn}>Sign in</Button>
            </div>
          </>
        )}

        {mode === "forgot" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <Field label="Work email">
              <Input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" />
            </Field>
            <Button variant="primary" size="lg" onClick={() => setMode("sent")}>Send reset link</Button>
            <Button variant="ghost" size="lg" onClick={() => setMode("signin")}>← Back to sign in</Button>
          </div>
        )}

        {mode === "sent" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "14px 16px", background: "var(--green-50)", border: "1px solid var(--green-100)", borderRadius: "var(--radius-md)", color: "var(--green-700)", fontSize: 13 }}>
              <Icon name="mail-check" size={16} />
              Email sent. Check your inbox.
            </div>
            <Button variant="secondary" size="lg" onClick={() => setMode("signin")}>← Back to sign in</Button>
          </div>
        )}

        <div style={{ marginTop: 40, fontSize: 12, color: "var(--fg-3)" }}>
          Need access? <a href="#">Ask your admin</a> · <a href="#">Terms</a> · <a href="#">Privacy</a>
        </div>
      </div>

      {/* marketing panel */}
      <div style={{
        background: "linear-gradient(160deg, #15224F 0%, #1A2C6C 35%, #2F4FCB 80%, #4F70E0 100%)",
        position: "relative", overflow: "hidden",
        display: "flex", flexDirection: "column", justifyContent: "flex-end",
        padding: 56, color: "#fff",
      }}>
        {/* subtle grain via repeating overlay */}
        <div style={{ position: "absolute", inset: 0, background: "radial-gradient(80% 60% at 80% 10%, rgba(255,255,255,0.18), transparent 70%), radial-gradient(60% 50% at 10% 90%, rgba(0,0,0,0.25), transparent 70%)" }} />
        <div style={{ position: "absolute", top: 56, right: 56, display: "flex", alignItems: "center", gap: 8, color: "rgba(255,255,255,0.7)", fontSize: 12 }}>
          <Icon name="shield-check" size={14} />
          SOC 2 · SAML SSO · audit log
        </div>
        <div style={{ position: "relative" }}>
          <blockquote style={{ margin: 0, fontFamily: "var(--font-serif)", fontSize: 26, lineHeight: 1.35, fontWeight: 500, letterSpacing: "-0.01em", maxWidth: 460 }}>
            “We replaced four spreadsheets and a Slack channel with WorkTrack. Daily reports take 90 seconds and managers finally see what shipped.”
          </blockquote>
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 24 }}>
            <Avatar name="Marco Velez" size={36} />
            <div style={{ fontSize: 13 }}>
              <div style={{ fontWeight: 500 }}>Marco Velez</div>
              <div style={{ opacity: 0.75 }}>VP Engineering, Northwind</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

window.Login = Login;
