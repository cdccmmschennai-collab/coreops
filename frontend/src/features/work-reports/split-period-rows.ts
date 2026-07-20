/**
 * Split-Day row lifecycle — pure functions, no React and no react-hook-form.
 *
 * Split Day holds exactly two independent periods (First Half / Second Half),
 * and a WORKING half carries exactly ONE activity row. There is no "add
 * another activity" path in Split Day: the single row appears automatically
 * when the half starts working, and disappears only when the user switches the
 * half to a leave/off status and confirms the clear.
 *
 * The form keeps ONE flat `tasks` array with a per-row `day_part` stamp, so
 * every operation here is index/stamp based. The rules that matter:
 *
 *   - reconcile only ever ADDS, and only into a working half that has none.
 *     It never deletes, never trims a malformed period down to one row, and
 *     never rewrites a row's day_part (a First-Half row can never become a
 *     Second-Half row, and full_day rows are invisible to every function here).
 *   - a malformed period (>1 row, only reachable via a hand-made payload or a
 *     future regression) is PRESERVED and reported, never silently repaired —
 *     `validateHalfRowCounts` flags it and the caller blocks the save.
 *   - nothing mutates its input: every function returns a new array, or the
 *     SAME array reference when there is nothing to change. Callers rely on
 *     that identity to skip redundant form writes, which is what keeps a
 *     re-render from appending a duplicate row.
 *
 * Full Day is untouched by this module.
 */

export type HalfPart = "first_half" | "second_half";
export type RowPart = "full_day" | HalfPart;

export const HALF_PARTS: readonly HalfPart[] = ["first_half", "second_half"];

/** Human labels, mirrored from schemas.ts so this module stays dependency-free. */
const HALF_LABEL: Record<HalfPart, string> = {
  first_half: "First Half",
  second_half: "Second Half",
};

/** The only shape this module needs from a task row. */
export interface PartitionedRow {
  day_part: RowPart;
}

/** Whether each half is currently working (a non-no-activity status). */
export type WorkingByHalf = Record<HalfPart, boolean>;

// ── reading ────────────────────────────────────────────────────────────────

/** Indices (into the flat array) of the rows belonging to one half. */
export function indicesOfPart<T extends PartitionedRow>(
  rows: readonly T[],
  part: RowPart,
): number[] {
  const out: number[] = [];
  rows.forEach((row, i) => {
    if (row.day_part === part) out.push(i);
  });
  return out;
}

/** How many rows one half holds. */
export function countOfPart<T extends PartitionedRow>(
  rows: readonly T[],
  part: RowPart,
): number {
  return indicesOfPart(rows, part).length;
}

// ── reconciliation (the auto-created primary row) ───────────────────────────

/**
 * Bring ONE half in line with its working state.
 *
 * Working + no row  -> append exactly one empty row stamped for this half.
 * Working + one row -> unchanged (an existing/loaded row is always preserved).
 * Working + >1 rows -> unchanged. Malformed data is preserved for the user to
 *                      fix; appending a third row would compound the problem.
 * Non-working       -> unchanged. Clearing is never automatic — it goes
 *                      through the explicit confirmation flow (`clearHalf`),
 *                      so a mis-click can't destroy entered work.
 *
 * Returns the SAME array reference when nothing changed, so a caller can cheaply
 * detect a no-op and skip writing back to the form. That identity check is what
 * makes repeated reconciliation on every render idempotent.
 */
export function reconcileHalf<T extends PartitionedRow>(
  rows: readonly T[],
  part: HalfPart,
  working: boolean,
  makeEmptyRow: () => T,
): readonly T[] {
  if (!working) return rows;
  if (countOfPart(rows, part) !== 0) return rows;
  return [...rows, { ...makeEmptyRow(), day_part: part }];
}

/**
 * Reconcile both halves in one pass (the order is irrelevant — each half only
 * ever appends its own row). Same identity contract as `reconcileHalf`.
 */
export function reconcileHalves<T extends PartitionedRow>(
  rows: readonly T[],
  working: WorkingByHalf,
  makeEmptyRow: () => T,
): readonly T[] {
  let next = rows;
  for (const part of HALF_PARTS) {
    next = reconcileHalf(next, part, working[part], makeEmptyRow);
  }
  return next;
}

// ── clearing (Working -> Leave/Off, after confirmation) ─────────────────────

/**
 * Drop every row of ONE half, leaving the other half and any full_day rows
 * exactly as they were. Called only after the user confirms the switch to a
 * leave/off status. Returns the same reference when the half is already empty.
 */
export function clearHalf<T extends PartitionedRow>(
  rows: readonly T[],
  part: HalfPart,
): readonly T[] {
  if (countOfPart(rows, part) === 0) return rows;
  return rows.filter((row) => row.day_part !== part);
}

// ── validation ─────────────────────────────────────────────────────────────

export type HalfIssueKind =
  /** Working half with no activity row. */
  | "missing"
  /** More than one row in a half — malformed, preserved, blocks save. */
  | "too_many"
  /** Non-working half that still carries rows. */
  | "unexpected";

export interface HalfActivityIssue {
  part: HalfPart;
  kind: HalfIssueKind;
  count: number;
  message: string;
}

function issueMessage(part: HalfPart, kind: HalfIssueKind): string {
  const label = HALF_LABEL[part];
  switch (kind) {
    case "missing":
      return `${label} must contain exactly one activity.`;
    case "too_many":
      return `${label} cannot contain more than one activity.`;
    case "unexpected":
      return `${label} is not a working half and cannot contain any activity.`;
  }
}

/**
 * The strict Split-Day rule, in one place: a working half holds exactly one
 * row, a non-working half holds none. Returns every violation (both halves are
 * reported, so a user fixing one isn't ambushed by the other), in a stable
 * First-Half-then-Second-Half order. An empty array means the report's period
 * rows are valid.
 *
 * `full_day` rows are ignored entirely — Split-Day validation never inspects,
 * counts or rejects them.
 */
export function validateHalfRowCounts<T extends PartitionedRow>(
  rows: readonly T[],
  working: WorkingByHalf,
): HalfActivityIssue[] {
  const issues: HalfActivityIssue[] = [];
  for (const part of HALF_PARTS) {
    const count = countOfPart(rows, part);
    const kind: HalfIssueKind | null = working[part]
      ? count === 0
        ? "missing"
        : count > 1
          ? "too_many"
          : null
      : count > 0
        ? "unexpected"
        : null;
    if (kind) {
      issues.push({ part, kind, count, message: issueMessage(part, kind) });
    }
  }
  return issues;
}

/** True when a half carries more rows than Split Day allows. */
export function hasMalformedHalf<T extends PartitionedRow>(
  rows: readonly T[],
): boolean {
  return HALF_PARTS.some((part) => countOfPart(rows, part) > 1);
}
