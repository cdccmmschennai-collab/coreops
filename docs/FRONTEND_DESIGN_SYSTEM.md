# Frontend Design System

> **Phase:** Frontend validation (no code). Brand-agnostic. Canonicalizes the tokens, components, and conventions used by every screen spec. Source: the design-system deck (`design-assets/deck/`), the UI-kit prototype (`design-assets/ui_kits/web_app/`), and `frontenddesign.md` §1. **Re-authors the missing token file (U-005)** as `styles/tokens.css`.

---

## 1. Design principles
**Calm, dense, competent.** One neutral (slate) carries ~90% of the UI; one blue accent for primary/focus/selection; green/amber/red for status only. No hover-lift, no glow, no bounce. The product **narrates state, never cheerleads** (sentence case, specific numbers).

## 2. Color tokens

| Token | Value | Use |
|---|---|---|
| `--blue-900` | `#1A2C6C` | brand mark |
| `--brand` / `--blue-600` | `#2F4FCB` | primary action, focus ring, selection, links |
| `--blue-50/100/500/700` | tint ramp | badges, hovers, active nav |
| `--slate-50` | `#F7F8FA` | app canvas |
| `--slate-100/150/300/400/500/700` | neutral ramp | borders, muted bg, secondary text |
| `--slate-900` / `--fg-1` | `#141821` | primary text |
| `--fg-2/3/4` | descending greys | secondary/tertiary/quaternary text |
| `--surface` | `#FFFFFF` | cards, inputs |
| `--green-600` `#079455` (+50/100/700) | success / present / approved |
| `--amber-600` `#DC6803` (+50/100/700) | warning / pending / leave |
| `--red-600` `#D92D20` (+50/100/700) | danger / absent / blocked |
| `--chart-1…6` | categorical | charts, project color dots |

**Avatar palette (deterministic by name):** `#4F70E0 #14B8A6 #8B5CF6 #F59E0B #EC4899 #10B981 #6366F1`.

## 3. Typography

- **Inter** = UI/body. **Source Serif 4** = display headings (H1–H4). **Geist Mono** (`--font-mono`) = code/IDs/version strings only. **Numeric/tabular data uses Inter with `tabular-nums`** (`.mono` utility — a misnomer; documented).

| Role | Size/weight | Family |
|---|---|---|
| H1 Display | 40 / 700 | Serif |
| H2 Heading (page titles) | 32 / 600 | Serif |
| H3 | 24 / 600 | Serif |
| H4 | 20 / 600 | Serif |
| Body Large | 16 / 400 | Inter |
| Body Base | 14 / 400 | Inter |
| Body Small | 12 / 400 | Inter |
| Caption | 11 / 400 | Inter |
| Tabular | Inter + `tnum` | hours, counts, IDs |

## 4. Spacing, radii, shadow, motion, layout

- **Spacing scale:** 4 · 8 · 12 · 16 · 20 · 24 · 32 (px).
- **Radii:** `sm` 6 · `md` 8 · `lg` 12 · `xl` 16 · `full` 9999.
- **Shadows:** `xs` (cards) → `xl` (modals); subtle, low-spread.
- **Motion:** 120–240ms, Linear-style ease-out; no scale/bounce; honor `prefers-reduced-motion`.
- **Layout tokens:** `--sidebar-w` ≈ 240px · `--topnav-h` ≈ 60px · `--page-max` (content max width) · focus ring `0 0 0 4px rgba(63,99,224,0.22)`.
- **Breakpoint:** 860px (mobile below).

> Exact px for radii/shadow/durations are reconstructed from the deck + `app.css`; finalize when `tokens.css` is authored (U-005).

## 5. Component catalog (states & variants)

| Component | Variants / states |
|---|---|
| **AppShell** | sidebar + sticky topnav + content; mobile = off-canvas sidebar + scrim |
| **Sidebar / NavItem** | sections (Workspace / Manage); active, hover, count badge; role-gated items |
| **TopNav** | breadcrumbs, ⌘K search, notifications bell, help, avatar menu; blur-sticky |
| **PageHeader** | serif title + sub + actions row |
| **Button** | `primary / secondary / ghost / danger / link`; `sm/md/lg`; icon L/R; loading; disabled |
| **Badge** | `neutral/info/success/warning/danger` + optional dot; lowercase |
| **Avatar / AvatarStack** | initials on deterministic color; presence dot; overflow +N |
| **Field / Input / Textarea / Select / PillSelect** | label, help, error; focus ring; disabled; invalid |
| **Tabs / Segmented** | active underline / segmented control (day/week/month); count chips |
| **DataTable** | header (uppercase caption), hover row, selected row, checkbox select, sticky header; empty/loading/error body |
| **Pagination** | "Showing X–Y of N" + Prev/Next (offset-based) |
| **FilterBar / FilterChip** | applied (blue) vs placeholder (outline); removable; "Clear all" |
| **SearchInput** | leading icon, ⌘K hint, debounced |
| **Modal** | scrim + 8px blur; header/body/footer; confirm/destructive |
| **Toast / ToastStack** | info/success/warning/danger; auto-dismiss ~4.2s; `aria-live` |
| **EmptyState** | glyph + title + description + action |
| **ErrorState** | icon + message + Retry |
| **Skeleton** | shimmer blocks matching layout |
| **Kpi** | label + tabular value + delta (up/down + trend icon) |
| **Icon** | Lucide, stroke 1.5, 16/20/24 |
| **Charts** | SVG: bars, stacked, donut, line, burn-down, heatmap, timeline |

## 6. Status → semantic mapping (consistent everywhere)

| Domain status | Badge variant |
|---|---|
| report: draft | neutral · submitted: info · approved: success · rejected: danger |
| attendance: present/wfh: success/info · leave/half_day: warning · holiday/weekend: neutral · absent: danger |
| project: active: success · at_risk/on_hold: warning · completed: info · archived: neutral |
| employee/user: active: success · on_leave: warning · invited: info · exited/inactive: neutral |

## 7. Data-display conventions
- Hours as `7h 45m`; counts right-aligned tabular; dates `May 24` + weekday sub; relative time for recent ("2 days ago"); IDs/codes in `--font-mono`.
- Money/hours never `float` rendering — format from `numeric`.
- Empty value = `—` (em dash), muted.

## 8. Voice
Sentence case. No exclamations/emoji-cheerleading. Specific numbers, concrete verbs. Errors are calm and actionable ("This report changed — reload to see the latest.").

## 9. Brand isolation
Wordmark/mark via a single `<Brand/>` component bound to `--product-name` / `NEXT_PUBLIC_PRODUCT_NAME`. No screen hardcodes a product name (D-001).

## 10. Accessibility baseline
Contrast ≥ AA (verify amber/secondary on tints); focus-visible rings; keyboard paths; `aria-live` regions; semantic tables/buttons; reduced-motion.

_Related: [`FRONTEND_ARCHITECTURE.md`](./FRONTEND_ARCHITECTURE.md) · [`frontenddesign.md`](./frontenddesign.md) · screen specs._
