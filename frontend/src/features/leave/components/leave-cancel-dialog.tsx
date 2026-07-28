"use client";

import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { AppError } from "@/lib/api-client";

import { useCancelLeave, useRequestLeaveCancellation } from "../hooks";
import { formatLeavePeriod, type LeaveRequest } from "../types";

/** `cancel` = pending leave, cancelled outright. `request` = approved leave,
 *  which a project manager has to sign off. Neither collects a reason. */
export type CancelDialogMode = "cancel" | "request";

interface Props {
  request: LeaveRequest;
  mode: CancelDialogMode;
  onClose: () => void;
}

const COPY: Record<CancelDialogMode, { title: string; body: string; confirm: string; dismiss: string }> = {
  cancel: {
    title: "Cancel leave request?",
    body: "Are you sure you want to cancel this pending leave request?",
    confirm: "Cancel Request",
    dismiss: "Keep Request",
  },
  request: {
    title: "Request leave cancellation?",
    body:
      "This leave has already been approved. Your Project Manager must approve the cancellation.",
    confirm: "Request Cancellation",
    dismiss: "Keep Leave",
  },
};

export function LeaveCancelDialog({ request, mode, onClose }: Props) {
  const copy = COPY[mode];
  const cancel = useCancelLeave();
  const requestCancellation = useRequestLeaveCancellation();
  const isPending = cancel.isPending || requestCancellation.isPending;

  async function onConfirm() {
    if (isPending) return;
    try {
      if (mode === "cancel") {
        await cancel.mutateAsync(request.id);
        toast.success("Leave request cancelled");
      } else {
        await requestCancellation.mutateAsync(request.id);
        toast.success("Cancellation requested. Your Project Manager will review it.");
      }
      onClose();
    } catch (err) {
      toast.error(
        err instanceof AppError ? err.message : "Could not update the leave request.",
      );
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        className="absolute inset-0 bg-foreground/40"
        onClick={() => !isPending && onClose()}
        aria-hidden
      />
      <Card className="relative z-10 w-full max-w-md shadow-xl">
        <CardHeader className="border-b border-border px-5 py-3.5">
          <CardTitle className="text-base">{copy.title}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 pt-5">
          <p className="text-sm text-muted-foreground">{copy.body}</p>
          <p className="text-sm">
            <span className="text-muted-foreground">Leave period: </span>
            <span className="font-medium">
              {formatLeavePeriod(request.start_date, request.end_date)}
            </span>
          </p>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={onClose} disabled={isPending}>
              {copy.dismiss}
            </Button>
            <Button
              variant="danger"
              onClick={() => void onConfirm()}
              loading={isPending}
              disabled={isPending}
            >
              {copy.confirm}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
