"use client";

import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { AppError } from "@/lib/api-client";

import { monthKeyLabel } from "@/features/attendance/selected-month";

import {
  useLeaveBalanceHistory,
  useSetLeaveAllocation,
  useSetLeaveBalance,
} from "../hooks";
import type { LeaveBalance } from "../types";

interface Props {
  /** One employee's balance FOR ONE MONTH. `balance.month` is the month being
   *  edited - taken from the row itself rather than from the page's selection, so
   *  the figures in the fields and the month both writes are stamped with can
   *  never come from two different months. */
  balance: LeaveBalance;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const MIN_BALANCE = -999.99;
const MAX_BALANCE = 999.99;
const MAX_ALLOCATION = 999.99;

/**
 * The PM's two decisions about one employee's leave, in one dialog.
 *
 *   Available Leave (70%)          Leave / month (30%)
 *   [      1.5      ]              [      2      ]
 *
 * They are different KINDS of decision, which is why they are two fields and two
 * calls rather than one form post:
 *
 *   Available Leave  a one-off CORRECTION to this month. The manager types the
 *                    balance they want the employee to have and the backend
 *                    stores the difference as an adjustment, so the monthly
 *                    accrual underneath survives. The frontend must never
 *                    compute that delta - it sends the target, exactly as this
 *                    dialog always has.
 *   Leave / month    the accrual RATE, effective-dated from the selected month
 *                    onwards. Earlier months keep the rate they were on; nothing
 *                    historical is rewritten, which is why the effective month is
 *                    printed under the field rather than left implied.
 *
 * ORDER MATTERS. The rate is written first: the correction's delta is computed
 * server-side against this month's automatic balance, and that balance includes
 * the rate. Correcting first would weigh the target against the old rate and
 * leave the balance off by the difference.
 */
export function LeaveBalanceEditDialog({ balance, open, onOpenChange }: Props) {
  const month = balance.month;
  const setBalance = useSetLeaveBalance();
  const setAllocation = useSetLeaveAllocation();
  const history = useLeaveBalanceHistory(balance.employee_id, { enabled: open });

  const [available, setAvailable] = React.useState(String(balance.available_leave));
  const [perMonth, setPerMonth] = React.useState(String(balance.monthly_allocation));
  const [reason, setReason] = React.useState("");

  // Reset the form whenever a different employee's dialog opens, or the month
  // under it changes - the figures in the fields belong to one employee-month.
  React.useEffect(() => {
    if (open) {
      setAvailable(String(balance.available_leave));
      setPerMonth(String(balance.monthly_allocation));
      setReason("");
    }
  }, [open, balance.available_leave, balance.monthly_allocation, balance.employee_id, month]);

  const value = Number(available);
  const allocation = Number(perMonth);

  // Balances may be negative (loss-of-pay): e.g. -0.5 half-day LOP, -2 excess.
  // The allocation may not - it is a grant, and a deduction is a correction.
  const balanceFieldValid =
    available.trim() !== "" &&
    Number.isFinite(value) &&
    value >= MIN_BALANCE &&
    value <= MAX_BALANCE;
  const allocationFieldValid =
    perMonth.trim() !== "" &&
    Number.isFinite(allocation) &&
    allocation >= 0 &&
    allocation <= MAX_ALLOCATION;

  const allocationChanged = allocationFieldValid && allocation !== balance.monthly_allocation;
  // A reason on its own still posts a correction, as it always did - the manager
  // took an action and said why, and the backend records it even when the figure
  // does not move.
  const wantsCorrection =
    balanceFieldValid && (value !== balance.available_leave || reason.trim().length > 0);

  const valid =
    balanceFieldValid &&
    allocationFieldValid &&
    (allocationChanged || wantsCorrection) &&
    (!wantsCorrection || reason.trim().length > 0);

  const pending = setAllocation.isPending || setBalance.isPending;

  async function onSave() {
    if (!valid) return;
    try {
      if (allocationChanged) {
        await setAllocation.mutateAsync({
          employeeId: balance.employee_id,
          body: { monthly_days: allocation, effective_from: month },
        });
      }
      if (wantsCorrection) {
        await setBalance.mutateAsync({
          employeeId: balance.employee_id,
          // The TARGET balance, not a delta. The backend derives the adjustment.
          body: { available_leave: value, reason: reason.trim(), month },
        });
      }
      toast.success(`Leave updated for ${monthKeyLabel(month)}`);
      onOpenChange(false);
    } catch (err) {
      toast.error(
        err instanceof AppError ? err.message : "Could not update leave for this month.",
      );
    }
  }

  const historyItems = history.data?.items ?? [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Edit leave balance</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label>Employee name</Label>
            <Input
              value={`${balance.employee_code} - ${balance.employee_name}`}
              readOnly
              disabled
            />
          </div>

          {/* The two editable figures, on one row: the correction is the larger
              decision and takes ~70% of the width, the rate ~30%. */}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-10">
            <div className="space-y-1.5 sm:col-span-7">
              <Label htmlFor="available-leave">Available Leave</Label>
              <Input
                id="available-leave"
                type="number"
                min={MIN_BALANCE}
                max={MAX_BALANCE}
                step={0.5}
                value={available}
                onChange={(e) => setAvailable(e.target.value)}
              />
              <p className="text-[11px] text-muted-foreground">
                Balance for {monthKeyLabel(month)}
                {!balance.in_ledger && " - no ledger for this month yet"}
              </p>
            </div>
            <div className="space-y-1.5 sm:col-span-3">
              <Label htmlFor="leave-per-month">Leave / month</Label>
              <Input
                id="leave-per-month"
                type="number"
                min={0}
                max={MAX_ALLOCATION}
                step={0.5}
                value={perMonth}
                onChange={(e) => setPerMonth(e.target.value)}
              />
              {/* Stated, never implied: this rate applies from the selected month
                  onwards and leaves earlier months exactly as they were. */}
              <p className="text-[11px] text-muted-foreground">
                From {monthKeyLabel(month)}
              </p>
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="balance-reason">
              Reason{" "}
              {wantsCorrection ? (
                <span className="text-destructive">*</span>
              ) : (
                <span className="font-normal text-muted-foreground">
                  (required to change Available Leave)
                </span>
              )}
            </Label>
            <Textarea
              id="balance-reason"
              rows={3}
              placeholder="Why is the balance changing? (required)"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </div>

          {historyItems.length > 0 && (
            <div className="space-y-2 border-t border-border pt-3">
              <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Recent changes
              </div>
              <ul className="max-h-40 space-y-2 overflow-y-auto text-sm">
                {historyItems.map((h) => (
                  <li key={h.id} className="rounded-md bg-secondary/40 px-3 py-2">
                    <div className="flex items-center justify-between gap-2">
                      <span className="tabular font-medium">
                        {h.old_balance ?? "-"} → {h.new_balance}
                      </span>
                      <span className="text-[11px] tabular text-muted-foreground">
                        {new Date(h.created_at).toLocaleString()}
                      </span>
                    </div>
                    <div className="mt-0.5 text-muted-foreground">{h.reason}</div>
                    {h.updated_by_name && (
                      <div className="mt-0.5 text-[11px] text-muted-foreground">
                        by {h.updated_by_name}
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={pending}>
            Cancel
          </Button>
          <Button onClick={() => void onSave()} disabled={!valid} loading={pending}>
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
