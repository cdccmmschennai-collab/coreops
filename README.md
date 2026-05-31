# CoreOps

> **CoreOps** is a *working codename / repository name only* — the final product name is undecided. See the [Naming Decision Record](./docs/architecture.md#14-naming-decision-record).

An enterprise **workforce operations platform**: structured daily reporting, attendance, leave, projects, analytics, and an audit-by-construction backbone. The product replaces spreadsheet-and-chat sprawl with one calm, dense system that turns captured effort into management signal.

## Status

**Documentation phase.** No application code exists yet. The design material under [`design-assets/`](./design-assets/) has been consolidated into an enterprise documentation set under [`docs/`](./docs/), which is the **single source of truth**. Implementation is gated on approval of [`docs/implementation-plan.md`](./docs/implementation-plan.md).

## Where to start

- **[docs/README.md](./docs/README.md)** — documentation index and reading order.
- **[docs/documentation-review-report.md](./docs/documentation-review-report.md)** — what was imported, conflicts, and gaps.
- **[docs/decisions.md](./docs/decisions.md)** — decisions, assumptions, and open questions awaiting answers.

## Repository layout

| Path | Contents |
|---|---|
| `docs/` | Single source of truth (architecture, design, roadmap, decisions, plan) |
| `design-assets/` | Imported source material (schema, UI kit, deck, brand) — **read-only reference** |
| `backend/` `frontend/` `database/` `docker/` `scripts/` | Scaffolding targets (empty; see [docs/PROJECT_STRUCTURE.md](./docs/PROJECT_STRUCTURE.md)) |

## Tech (decided so far)

- **Database:** PostgreSQL 14+ (16 recommended). Everything above the data tier — backend stack, API style, infra — is an **open decision** (`docs/decisions.md` §C).
