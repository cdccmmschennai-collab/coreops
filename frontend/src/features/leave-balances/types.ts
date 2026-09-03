/**
 * Leave balances, as the Phase 3 ledger reports them.
 *
 * EVERY FIGURE HERE IS A MONTH FIGURE. The server derives
 * `closing = carry_forward + allocation + adjustment - consumed` per calendar
 * month and sends the whole working, never a stored total. The frontend adds
 * nothing to it: there is no `previous + allocation` arithmetic anywhere in this
 * feature, because a second calculation is a second answer.
 *
 * `month` is always the first of the month, `YYYY-MM-DD`, and is echoed on every
 * response so a client can prove which month it is showing.
 */
export interface LeaveBalance {
  employee_id: string;
  employee_code: string;
  employee_name: string;
  /** The month this whole row describes (first of the month). */
  month: string;
  /** The month's closing balance - the "Available Leave" figure. */
  available_leave: number;
  /** The `Leave/month` in force for this month (0 when none is configured). */
  monthly_allocation: number;
  carry_forward: number;
  adjustment: number;
  consumed: number;
  /** False when the month precedes this employee's ledger. NOT a zero balance:
   *  there is no balance to state, and the UI shows "-". */
  in_ledger: boolean;
  ledger_start_month: string | null;
  last_updated: string | null;
}

export interface LeaveBalancePage {
  items: LeaveBalance[];
  total: number;
  limit: number;
  offset: number;
  /** The month the server resolved the request to. */
  month: string;
}

export interface MyLeaveBalance {
  employee_id: string;
  month: string;
  available_leave: number;
  monthly_allocation: number;
  carry_forward: number;
  adjustment: number;
  consumed: number;
  in_ledger: boolean;
  ledger_start_month: string | null;
  last_updated: string | null;
}

/** The PM correction. Still the TARGET balance the manager wants - the backend
 *  turns it into a signed adjustment so the monthly allocation underneath
 *  survives. The frontend must NOT compute the delta. */
export interface LeaveBalanceUpdateBody {
  available_leave: number;
  reason: string;
  /** Which month the correction belongs to (first of the month). Omitted means
   *  the current Chennai business month, resolved server-side. */
  month?: string;
}

/** `Leave/month`, effective-dated. Writing a new effective month leaves earlier
 *  months on the rate they were on - which is what stops a rate change from
 *  silently rewriting history. */
export interface LeaveAllocationUpdateBody {
  monthly_days: number;
  /** Must be a first-of-month; the API rejects anything else rather than
   *  quietly truncating it. */
  effective_from: string;
  note?: string | null;
}

export interface LeaveAllocation {
  id: string;
  employee_id: string;
  effective_from: string;
  monthly_days: number;
  note: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface LeaveBalanceHistory {
  id: string;
  employee_id: string;
  old_balance: number | null;
  new_balance: number;
  reason: string;
  updated_by: string | null;
  updated_by_name: string | null;
  created_at: string;
}

export interface LeaveBalanceHistoryPage {
  items: LeaveBalanceHistory[];
  total: number;
  limit: number;
  offset: number;
}

export type SortDir = "asc" | "desc";

export interface LeaveBalanceListParams {
  q?: string;
  sort_dir?: SortDir;
  /** Any date in the month to report; omitted asks for the current business
   *  month. The tab always sends the 1st. */
  month?: string;
  limit: number;
  offset: number;
}

// ---------- pure helpers ----------------------------------------------------

/**
 * Whether a number is a whole or half day - the only quantities leave comes in.
 *
 * The mirror of `app/shared/leave_units.py`, which is the real guard: this one
 * only decides whether the Save button is enabled and what the field says. The
 * API refuses a bad value whatever the browser did, because `step="0.5"` on an
 * input governs the little arrows and nothing else - a typed 2.4 passes it.
 *
 * Multiplied by 2 and tested against a rounded copy rather than using `% 0.5`,
 * which inherits binary floating-point error (`2.4 % 0.5` is 0.3999999999999999,
 * not 0.4, and the comparisons get worse from there). `x * 2` is exact for every
 * value a manager can type into this field.
 */
export function isHalfStep(value: number): boolean {
  if (!Number.isFinite(value)) return false;
  return Math.abs(value * 2 - Math.round(value * 2)) < 1e-9;
}

/** How a balance figure prints: `1.5`, `-2`, `0` - and `-` for a month that
 *  precedes the employee's ledger, which is not the same as zero.
 *
 *  Zero and negative balances print exactly as they are. Nothing in this module
 *  hides or blocks them, and nothing on the server does either: a leave approval
 *  no longer weighs the balance, so a genuine approval may overdraw the pool and
 *  a negative figure here is an ordinary state, not an error to be styled as
 *  one. It is offset by the next month's accrual. */
export function formatBalance(
  value: number,
  inLedger = true,
): string {
  if (!inLedger) return "-";
  // Trims a trailing ".00"/".50" to "1"/"1.5" without touching a real integer.
  return String(Number(value.toFixed(2)));
}
