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

import { useDeactivateEmployee } from "../hooks";
import type { Employee } from "../types";

export function DeactivateDialog({
  employee,
  onOpenChange,
  onDone,
}: {
  employee: Employee | null;
  onOpenChange: (open: boolean) => void;
  onDone?: () => void;
}) {
  const mutation = useDeactivateEmployee();

  async function confirm() {
    if (!employee) return;
    try {
      await mutation.mutateAsync(employee.id);
      toast.success(`${employee.full_name} deactivated`);
      onDone?.();
      onOpenChange(false);
    } catch (error) {
      toast.error(error instanceof AppError ? error.message : "Could not deactivate employee.");
    }
  }

  return (
    <AlertDialog open={employee !== null} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Deactivate employee?</AlertDialogTitle>
          <AlertDialogDescription>
            {employee?.full_name} will be marked exited and removed from active
            lists. An admin can recreate the record later.
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
            Deactivate
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
