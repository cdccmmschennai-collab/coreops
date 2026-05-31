/* Toast system + mobile-aware shell utilities */

function useToasts() {
  const [toasts, setToasts] = useState([]);
  const show = (t) => {
    const id = Math.random().toString(36).slice(2);
    setToasts((s) => [...s, { id, ...t }]);
    setTimeout(() => setToasts((s) => s.filter((x) => x.id !== id)), t.duration || 4200);
  };
  const dismiss = (id) => setToasts((s) => s.filter((x) => x.id !== id));
  return { toasts, show, dismiss };
}

function ToastStack({ toasts, dismiss }) {
  return (
    <div style={{ position: "fixed", bottom: 24, right: 24, zIndex: 200, display: "flex", flexDirection: "column", gap: 10, maxWidth: 380 }}>
      {toasts.map((t) => {
        const { bg, fg, icon } = TOAST_STYLES[t.variant || "info"];
        return (
          <div key={t.id} style={{
            background: "#fff", border: "1px solid var(--border)", borderRadius: "var(--radius-lg)",
            boxShadow: "var(--shadow-lg)",
            display: "flex", gap: 12, padding: 14, alignItems: "flex-start",
            animation: "toastIn 240ms var(--ease-out)",
          }}>
            <div style={{ width: 28, height: 28, borderRadius: 6, background: bg, color: fg, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
              <Icon name={icon} size={16} />
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 13, fontWeight: 600 }}>{t.title}</div>
              {t.desc && <div style={{ fontSize: 12, color: "var(--fg-2)", marginTop: 2 }}>{t.desc}</div>}
            </div>
            <button className="icon-btn" onClick={() => dismiss(t.id)} style={{ width: 24, height: 24 }}><Icon name="x" size={12} /></button>
          </div>
        );
      })}
      <style>{`@keyframes toastIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }`}</style>
    </div>
  );
}

const TOAST_STYLES = {
  info:    { bg: "var(--blue-50)",  fg: "var(--blue-700)",  icon: "info" },
  success: { bg: "var(--green-50)", fg: "var(--green-700)", icon: "check-circle-2" },
  warning: { bg: "var(--amber-50)", fg: "var(--amber-700)", icon: "alert-triangle" },
  danger:  { bg: "var(--red-50)",   fg: "var(--red-700)",   icon: "circle-alert" },
};

function useMediaQuery(q) {
  const [match, setMatch] = useState(() => typeof window !== "undefined" && window.matchMedia(q).matches);
  useEffect(() => {
    const m = window.matchMedia(q);
    const cb = () => setMatch(m.matches);
    m.addEventListener("change", cb);
    return () => m.removeEventListener("change", cb);
  }, [q]);
  return match;
}

Object.assign(window, { useToasts, ToastStack, useMediaQuery });
