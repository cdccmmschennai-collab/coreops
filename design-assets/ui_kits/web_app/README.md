# WorkTrack Web App — UI Kit

A hi-fi recreation of the WorkTrack enterprise web app. Use this as a click-through prototype and as a reference library when building new flows.

## Run

Open `index.html` — it switches between the seven core screens via the sidebar. State is in-memory; refreshing returns you to the dashboard.

## Screens

| File | Route | What it shows |
|------|-------|---------------|
| `screens/Login.jsx` | / | Credentials + SSO panel |
| `screens/Dashboard.jsx` | /home | Today, this week, recent reports, my projects |
| `screens/ReportForm.jsx` | /report/new | Multi-project entry, hours, blockers |
| `screens/History.jsx` | /reports | Filterable, exportable table of past reports |
| `screens/Team.jsx` | /team | Manager view — load, review queue |
| `screens/Analytics.jsx` | /analytics | Charts: hours by category, project burn |
| `screens/Admin.jsx` | /admin | People & projects management |
| `screens/ProjectDetail.jsx` | /projects/:id | Project hub — contributors, status |

## Components (`components.jsx`)

All components are global on `window` so screen files can use them without imports.

| Component | Purpose |
|-----------|---------|
| `<AppShell>` | Sidebar + top nav + content frame |
| `<Sidebar>`, `<NavItem>` | Left rail navigation |
| `<TopNav>` | Sticky top bar with search, notifications, user menu |
| `<Card>`, `<CardHeader>`, `<CardBody>` | Surface primitives |
| `<Button>` | Primary / secondary / ghost / danger / link variants + sizes |
| `<Badge>` | Status pill — variant prop maps to semantic color |
| `<Avatar>`, `<AvatarStack>` | Initials avatars with deterministic color |
| `<Field>`, `<Input>`, `<Textarea>`, `<Select>` | Form controls |
| `<DataTable>`, `<Th>`, `<Td>` | Tables with hover + selected row |
| `<Icon name="..." size={16} />` | Lucide wrapper |
| `<Tabs>`, `<Segmented>` | Tabbed nav |
| `<PageHeader>` | Title + actions row |
| `<EmptyState>` | Standard empty pattern |
| `<Modal>` | Centered modal with scrim + 8px blur |

## Notes

- No real backend. Data is seeded inline in each screen file.
- Icons via Lucide CDN. If swapped for a bespoke set, replace `<Icon>` only.
- Built against `../../colors_and_type.css` — same tokens as the design system root.
