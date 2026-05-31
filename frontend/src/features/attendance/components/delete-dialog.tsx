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

import { useDeleteAttendance } from "../hooks";
import type { Attendance } from "../types";

export function DeleteDialog({
  record,
  onOpenChange,
  onDone,
}: {
  record: Attendance | null;
  onOpenChange: (open: boolean) => void;
  onDone?: () => void;
}) {
  const mutation = useDeleteAttendance();

  async function confirm() {
    if (!record) return;
    try {
      await mutation.mutateAsync(record.id);
      toast.success("Attendance record deleted");
      onDone?.();
      onOpenChange(false);
    } catch (error) {
      toast.error(error instanceof AppError ? error.message : "Could not delete record.");
    }
  }

  return (
    <AlertDialog open={record !== null} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete attendance record?</AlertDialogTitle>
          <AlertDialogDescription>
            This permanently removes the record for {record?.attendance_date}.
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
