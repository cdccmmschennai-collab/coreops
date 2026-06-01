"use client";

import { toast } from "sonner";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { AppError } from "@/lib/api-client";

import { useDeleteWorkReport } from "../hooks";
import type { WorkReport } from "../types";

export function DeleteDialog({
  report,
  onOpenChange,
  onDone,
}: {
  report: WorkReport | null;
  onOpenChange: (open: boolean) => void;
  onDone?: () => void;
}) {
  const mutation = useDeleteWorkReport();

  async function confirm() {
    if (!report) return;
    try {
      await mutation.mutateAsync(report.id);
      toast.success("Draft report deleted");
      onDone?.();
      onOpenChange(false);
    } catch (error) {
      toast.error(error instanceof AppError ? error.message : "Could not delete report.");
    }
  }

  return (
    <AlertDialog open={report !== null} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete draft report?</AlertDialogTitle>
          <AlertDialogDescription>
            This permanently removes the draft for {report?.report_date}.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            onClick={(e) => {
              e.preventDefault();
              void confirm();
            }}
            disabled={mutation.isPending}
          >
            Delete
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
