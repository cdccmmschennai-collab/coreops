// Daily count columns for the PM Weekly Activity Report preview — summed across
// the day's activities (the per-activity breakdown lives only in the Excel
// export's dynamic columns). Order is a contract shared with the Excel export
// (export.py _BLOCK): Tags | Docs | BOM | Spares | Pages | Records, sitting
// after Activity Summary and before Remarks. Exported (and unit-tested in
// columns.test.ts) so the order can never silently drift.

import type { ActivityCell } from "./types";

export type CountKey = "tags" | "docs" | "bom" | "spares" | "pages" | "records";

export const COUNT_COLUMNS: ReadonlyArray<{ label: string; key: CountKey }> = [
  { label: "Tags", key: "tags" },
  { label: "Docs", key: "docs" },
  { label: "BOM", key: "bom" },
  { label: "Spares", key: "spares" },
  { label: "Pages", key: "pages" },
  { label: "Records", key: "records" },
];

/** Sum one count key across a day's activities, treating a missing value as 0. */
export function sumCount(acts: ActivityCell[], key: CountKey): number {
  return acts.reduce((s, a) => s + (a[key] ?? 0), 0);
}
