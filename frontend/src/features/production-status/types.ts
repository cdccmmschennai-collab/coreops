import type { components } from "@/types/openapi";

// Straight from the live API contract (openapi-typescript output), same as
// every other feature. The read shape is already fully resolved server-side -
// project/plant labels, the activity name and `created_by_name` all arrive with
// the row, so nothing here ever looks a user id up to find a person.
export type ProductionStatus = components["schemas"]["ProductionStatusOut"];

// The POST body. It carries only what a human entered. `project_id` is not a
// field: the project comes from the path (which is what the caller is
// authorized against), and the author is resolved from the token - which is why
// there is no `created_by` here either.
export type ProductionStatusCreateBody =
  components["schemas"]["ProductionStatusCreate"];

/** Optional narrowing for the history read. */
export interface ProductionStatusHistoryParams {
  /** An Activity Master activity's id. */
  activityId?: string;
  /** A typed activity's own name - the other way a record names its activity. */
  activityLabel?: string;
  revision?: string;
}

// The PM cumulative report (Phase 4). A flat, fully-rendered row - the plant
// label, the activity label, the status wording, the author's name and the
// S.NO are all resolved server-side, because the .xlsx is rendered from this
// same dataset and the two must not be able to disagree.
export type ProductionStatusReport =
  components["schemas"]["ProductionStatusReportOut"];

export type ProductionStatusReportRow =
  components["schemas"]["ProductionStatusReportRow"];
