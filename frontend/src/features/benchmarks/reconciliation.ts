// Backlog reconciliation for the weekly Benchmark Performance rows.
//
// Pure, framework-free logic (extracted from the productivity widget so it can
// be unit-checked in isolation). Operates only on the current cycle's `daily`
// rows the benchmark ledger returns — which are already Fri..Thu scoped — so
// reconciliation is inherently same-cycle-only and resets every Friday with
// the ledger.

import type { DailyBenchmarkRow } from "./types";

export function rowKey(row: DailyBenchmarkRow): string {
  return `${row.date}__${row.sub_activity_id}`;
}

// Reconciliation outcome for one benchmark day-row.
export interface Recon {
  // Pending remaining after later days' excess is applied to this day's
  // deficit (0 ⇒ fully cleared, so the row reads as Completed).
  effectivePending: number;
  // True when this day's own deficit was wiped out by a *later* day's excess
  // (i.e. it was short on the day but recovered since).
  reconciled: boolean;
  // Units of *earlier* days' backlog this day's excess paid down — set only
  // on the surplus day, for the "cleared earlier backlog" note.
  clearedBacklog: number;
  unit: string | null;
}

// Backlog reconciliation at the sub-activity level. The benchmark engine
// clamps each day's pending independently (a good Thursday must not erase a
// bad Wednesday in the *productivity* math), so a day that fell short keeps
// reporting pending even after a later day made the shortfall up. This walks
// each sub-activity's days in date order and lets a later day's excess pay
// down earlier outstanding deficits, oldest first: the earlier row's
// effectivePending drops and, once it hits zero, that row reads as Completed.
//
// Excess only ever flows backward to cover prior deficits — leftover excess
// is discarded, never banked as a credit against a *future* day (a future
// deficit can only be cleared by an even-later excess, never by a past one).
// Display-only: it never feeds back into target/actual/pending or productivity.
//
// Rows are grouped strictly by `sub_activity_id` (project is intentionally not
// part of the key — the benchmark target is per-employee-per-sub-activity, and
// the ledger already sums actual across projects per day).
export function computeReconciliation(daily: DailyBenchmarkRow[]): Map<string, Recon> {
  const bySub = new Map<string, DailyBenchmarkRow[]>();
  for (const row of daily) {
    const arr = bySub.get(row.sub_activity_id);
    if (arr) arr.push(row);
    else bySub.set(row.sub_activity_id, [row]);
  }

  const recon = new Map<string, Recon>();
  for (const rows of bySub.values()) {
    const sorted = [...rows].sort((a, b) => a.date.localeCompare(b.date));
    // Outstanding earlier deficits, oldest first, each linked to its row key.
    const outstanding: { key: string; remaining: number }[] = [];
    for (const row of sorted) {
      const key = rowKey(row);
      const actual = Number(row.actual);
      const target = Number(row.target);
      const deficit = Math.max(0, target - actual);
      let surplus = Math.max(0, actual - target);

      recon.set(key, {
        effectivePending: deficit,
        reconciled: false,
        clearedBacklog: 0,
        unit: row.benchmark_unit,
      });

      // This day's excess pays down the oldest outstanding deficits first.
      let cleared = 0;
      while (surplus > 0 && outstanding.length > 0) {
        const head = outstanding[0];
        const applied = Math.min(surplus, head.remaining);
        head.remaining -= applied;
        surplus -= applied;
        cleared += applied;
        const earlier = recon.get(head.key)!;
        earlier.effectivePending = head.remaining;
        if (head.remaining <= 0) {
          earlier.reconciled = true;
          outstanding.shift();
        }
      }
      // Leftover `surplus` is intentionally dropped here — no forward credit.
      if (cleared > 0) recon.get(key)!.clearedBacklog = cleared;
      if (deficit > 0) outstanding.push({ key, remaining: deficit });
    }
  }
  return recon;
}
