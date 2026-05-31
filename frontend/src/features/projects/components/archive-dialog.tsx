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

import { useArchiveProject } from "../hooks";
import type { Project } from "../types";

export function ArchiveDialog({
  project,
  onOpenChange,
  onDone,
}: {
  project: Project | null;
  onOpenChange: (open: boolean) => void;
  onDone?: () => void;
}) {
  const mutation = useArchiveProject();

  async function confirm() {
    if (!project) return;
    try {
      await mutation.mutateAsync(project.id);
      toast.success(`${project.name} archived`);
      onDone?.();
      onOpenChange(false);
    } catch (error) {
      toast.error(error instanceof AppError ? error.message : "Could not archive project.");
    }
  }

  return (
    <AlertDialog open={project !== null} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Archive project?</AlertDialogTitle>
          <AlertDialogDescription>
            {project?.name} will be archived and hidden from active lists. You can
            still find it by filtering on the archived status.
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
            Archive
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
