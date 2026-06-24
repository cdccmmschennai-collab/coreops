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

import { useLeaveBalanceHistory, useSetLeaveBalance } from "../hooks";
import type { LeaveBalance } from "../types";

interface Props {
  balance: LeaveBalance;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function LeaveBalanceEditDialog({ balance, open, onOpenChange }: Props) {
  const setBalance = useSetLeaveBalance();
  const history = useLeaveBalanceHistory(balance.employee_id, { enabled: open });

  const [available, setAvailable] = React.useState(String(balance.available_leave));
  const [reason, setReason] = React.useState("");

  // Reset the form whenever a different employee's dialog opens.
  React.useEffect(() => {
    if (open) {
      setAvailable(String(balance.available_leave));
      setReason("");
    }
  }, [open, balance.available_leave, balance.employee_id]);

  const value = Number(available);
  // Balances may be negative (loss-of-pay): e.g. -0.5 half-day LOP, -2 excess.
  const valid =
    available.trim() !== "" &&
    Number.isFinite(value) &&
    value >= -999.99 &&
    value <= 999.99 &&
    reason.trim().length > 0;

  async function onSave() {
    if (!valid) return;
    try {
      await setBalance.mutateAsync({
        employeeId: balance.employee_id,
        body: { available_leave: value, reason: reason.trim() },
      });
      toast.success("Leave balance updated");
      onOpenChange(false);
    } catch (err) {
      toast.error(err instanceof AppError ? err.message : "Could not update balance.");
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
            <Input value={balance.employee_name} readOnly disabled />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="available-leave">Available leave</Label>
            <Input
              id="available-leave"
              type="number"
              min={-999.99}
              max={999.99}
              step={0.5}
              value={available}
              onChange={(e) => setAvailable(e.target.value)}
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="balance-reason">
              Reason <span className="text-destructive">*</span>
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
                        {h.old_balance ?? "—"} → {h.new_balance}
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
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={() => void onSave()} disabled={!valid} loading={setBalance.isPending}>
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
