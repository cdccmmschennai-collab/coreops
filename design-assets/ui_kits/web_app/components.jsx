/* WorkTrack — shared components.
   Exported to window so screen files don't need imports. */

const { useState, useEffect, useRef, useMemo, createContext, useContext } = React;

/* ---------- Icon (Lucide wrapper) ---------- */
function Icon({ name, size = 16, strokeWidth = 1.5, style, className }) {
  const ref = useRef(null);
  useEffect(() => {
    if (!ref.current || !window.lucide) return;
    ref.current.innerHTML = "";
    const el = document.createElement("i");
    el.setAttribute("data-lucide", name);
    ref.current.appendChild(el);
    window.lucide.createIcons({
      attrs: { width: size, height: size, "stroke-width": strokeWidth },
    });
  }, [name, size, strokeWidth]);
  return (
    <span
      ref={ref}
      className={className}
      style={{ display: "inline-flex", alignItems: "center", lineHeight: 0, ...style }}
    />
  );
}

/* ---------- Button ---------- */
function Button({ variant = "secondary", size = "md", icon, iconRight, children, ...props }) {
  const cls = ["btn", `btn-${variant}`, size === "sm" && "btn-sm", size === "lg" && "btn-lg"].filter(Boolean).join(" ");
  return (
    <button className={cls} {...props}>
      {icon && <Icon name={icon} size={size === "sm" ? 13 : 14} />}
      {children}
      {iconRight && <Icon name={iconRight} size={size === "sm" ? 13 : 14} />}
    </button>
  );
}

/* ---------- Card ---------- */
function Card({ children, style }) { return <div className="card" style={style}>{children}</div>; }
function CardHeader({ title, meta, action }) {
  return (
    <div className="card-header">
      <span className="title">{title}</span>
      {meta && <span className="meta">{meta}</span>}
      {action && <span style={{ marginLeft: "auto" }}>{action}</span>}
    </div>
  );
}
function CardBody({ children, style }) { return <div className="card-body" style={style}>{children}</div>; }

/* ---------- Badge ---------- */
function Badge({ variant = "neutral", dot = true, children }) {
  const dotColor = {
    neutral: "var(--slate-400)",
    info: "var(--blue-500)",
    success: "var(--green-500)",
    warning: "var(--amber-500)",
    danger: "var(--red-500)",
  }[variant];
  return (
    <span className={`badge badge-${variant}`}>
      {dot && <span className="dot" style={{ background: dotColor }} />}
      {children}
    </span>
  );
}

/* ---------- Avatar ---------- */
const AVATAR_COLORS = ["#4F70E0", "#14B8A6", "#8B5CF6", "#F59E0B", "#EC4899", "#10B981", "#6366F1"];
function avatarColor(name) {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) % AVATAR_COLORS.length;
  return AVATAR_COLORS[h];
}
function initials(name) {
  return name.split(/\s+/).slice(0, 2).map((p) => p[0]).join("").toUpperCase();
}
function Avatar({ name = "", size = 28, presence, style }) {
  const fontSize = Math.round(size * 0.38);
  return (
    <span
      className="avatar"
      title={name}
      style={{
        width: size, height: size, background: avatarColor(name), fontSize,
        position: presence ? "relative" : undefined, ...style,
      }}
    >
      {initials(name)}
      {presence && (
        <span style={{
          position: "absolute", right: -1, bottom: -1,
          width: Math.max(6, size * 0.25), height: Math.max(6, size * 0.25),
          background: presence === "online" ? "var(--green-500)" : "var(--amber-500)",
          borderRadius: "50%", border: "1.5px solid #fff",
        }} />
      )}
    </span>
  );
}
function AvatarStack({ names, size = 24, max = 4 }) {
  const visible = names.slice(0, max);
  const extra = names.length - visible.length;
  return (
    <span className="avatar-stack">
      {visible.map((n, i) => <Avatar key={i} name={n} size={size} />)}
      {extra > 0 && (
        <span className="avatar" style={{ width: size, height: size, background: "var(--slate-100)", color: "var(--fg-2)", fontSize: Math.round(size * 0.4) }}>
          +{extra}
        </span>
      )}
    </span>
  );
}

/* ---------- Form ---------- */
function Field({ label, help, error, children }) {
  return (
    <div>
      {label && <label className="field-label">{label}</label>}
      {children}
      {error ? <div className="field-error">{error}</div> : help && <div className="field-help">{help}</div>}
    </div>
  );
}
function Input(props) { return <input className="input" {...props} />; }
function Textarea(props) { return <textarea className="textarea" {...props} />; }
function Select({ value, placeholder, onClick, open, children }) {
  return (
    <div className={`select-trigger${open ? " open" : ""}`} onClick={onClick} tabIndex={0}>
      <span style={{ color: value ? "var(--fg-1)" : "var(--fg-4)" }}>{value || placeholder || "Select…"}</span>
      <Icon name="chevron-down" size={14} style={{ color: "var(--fg-3)" }} />
    </div>
  );
}

/* ---------- Tabs / Segmented ---------- */
function Tabs({ items, value, onChange }) {
  return (
    <div className="tabs">
      {items.map((it) => (
        <div key={it.value} className={`tab${value === it.value ? " active" : ""}`} onClick={() => onChange(it.value)}>
          {it.label}{it.count != null && <span className="count">{it.count}</span>}
        </div>
      ))}
    </div>
  );
}
function Segmented({ items, value, onChange }) {
  return (
    <div className="segmented">
      {items.map((it) => (
        <div key={it.value} className={`segmented-item${value === it.value ? " active" : ""}`} onClick={() => onChange(it.value)}>{it.label}</div>
      ))}
    </div>
  );
}

/* ---------- Modal ---------- */
function Modal({ open, onClose, title, description, children, footer }) {
  if (!open) return null;
  return (
    <div className="modal-scrim" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>{title}</h2>
          {description && <p>{description}</p>}
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-footer">{footer}</div>}
      </div>
    </div>
  );
}

/* ---------- PageHeader ---------- */
function PageHeader({ title, sub, actions }) {
  return (
    <div className="page-header">
      <div>
        <h1>{title}</h1>
        {sub && <div className="sub">{sub}</div>}
      </div>
      {actions && <div className="actions">{actions}</div>}
    </div>
  );
}

/* ---------- EmptyState ---------- */
function EmptyState({ icon = "inbox", title, description, action }) {
  return (
    <div className="empty">
      <div className="glyph"><Icon name={icon} size={20} /></div>
      <h3>{title}</h3>
      {description && <p>{description}</p>}
      {action}
    </div>
  );
}

/* ---------- KPI ---------- */
function Kpi({ label, value, delta }) {
  return (
    <div className="kpi">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
      {delta && (
        <div className={`delta ${delta.dir}`}>
          <Icon name={delta.dir === "up" ? "trending-up" : "trending-down"} size={12} />
          {delta.text}
        </div>
      )}
    </div>
  );
}

Object.assign(window, {
  Icon, Button, Card, CardHeader, CardBody, Badge, Avatar, AvatarStack,
  Field, Input, Textarea, Select, Tabs, Segmented, Modal, PageHeader, EmptyState, Kpi,
});
