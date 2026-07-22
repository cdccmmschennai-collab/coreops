"use client";

import * as React from "react";
import { Lock, Users } from "lucide-react";
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
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { AppError } from "@/lib/api-client";
import type { ActivityMaster } from "@/features/activity-master/types";

import { useActivityAccess, useChangeAccessType, useGrantAccess } from "../hooks";
import type { EmployeeSearchResult } from "../types";
import { AuthorizedEmployeesTable } from "./authorized-employees-table";
import { EmployeeAccessSearch } from "./employee-access-search";

const PAGE = 20;

export function ActivityAccessTab({ activity }: { activity: ActivityMaster }) {
  const [offset, setOffset] = React.useState(0);
  // The tab only mounts when the PM opens it, so fetching here IS the lazy load.
  const query = useActivityAccess(activity.id, PAGE, offset, true);
  const readOnly = !activity.is_active;

  if (query.isLoading) {
    return <p className="p-4 text-sm text-muted-foreground">Loading access…</p>;
  }
  if (query.isError || !query.data) {
    return <p className="p-4 text-sm text-destructive">Could not load access details.</p>;
  }

  const config = query.data;

  return (
    <div className="space-y-4 p-4">
      <div>
        <h4 className="text-sm font-medium">Who can use this activity?</h4>
        <ul className="mt-1 space-y-0.5 text-sm text-muted-foreground">
          <li>
            <span className="font-medium text-foreground">Common</span> - all active
            employees can select this activity.
          </li>
          <li>
            <span className="font-medium text-foreground">Restricted</span> - only
            employees explicitly selected by a PM can select this activity.
          </li>
        </ul>
      </div>

      {readOnly && (
        <p className="rounded-md border border-border bg-muted/40 p-2 text-xs text-muted-foreground">
          This activity is inactive. Access is read-only - reactivate it to make changes.
        </p>
      )}

      {config.access_type === "COMMON" ? (
        <CommonState activity={activity} readOnly={readOnly} />
      ) : (
        <RestrictedState
          activity={activity}
          config={config}
          offset={offset}
          onOffsetChange={setOffset}
          readOnly={readOnly}
        />
      )}
    </div>
  );
}

// ── COMMON ───────────────────────────────────────────────────────────────────

function CommonState({
  activity,
  readOnly,
}: {
  activity: ActivityMaster;
  readOnly: boolean;
}) {
  const [open, setOpen] = React.useState(false);
  const [selected, setSelected] = React.useState<EmployeeSearchResult[]>([]);
  const changeType = useChangeAccessType(activity.id);

  async function restrict() {
    try {
      await changeType.mutateAsync({
        access_type: "RESTRICTED",
        employee_ids: selected.map((e) => e.id),
      });
      toast.success(`"${activity.name}" is now restricted`);
      setOpen(false);
      setSelected([]);
    } catch (err) {
      toast.error(err instanceof AppError ? err.message : "Could not restrict activity.");
    }
  }

  return (
    <div className="flex items-center gap-3 rounded-md border border-border bg-muted/30 p-3">
      <Users className="h-4 w-4 text-muted-foreground" />
      <p className="flex-1 text-sm text-muted-foreground">
        Every active employee can currently use this activity.
      </p>
      <Button size="sm" variant="secondary" disabled={readOnly} onClick={() => setOpen(true)}>
        <Lock className="h-4 w-4" />
        Restrict
      </Button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Restrict &ldquo;{activity.name}&rdquo;</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Only selected employees will be able to use this activity. Existing reports
            will not be affected. Search and select at least one employee.
          </p>
          <div className="mt-3">
            <EmployeeAccessSearch
              activityId={activity.id}
              selected={selected}
              onChange={setSelected}
            />
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button
              loading={changeType.isPending}
              disabled={selected.length === 0}
              onClick={() => void restrict()}
            >
              Restrict to {selected.length || "…"} employee
              {selected.length === 1 ? "" : "s"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ── RESTRICTED ───────────────────────────────────────────────────────────────

function RestrictedState({
  activity,
  config,
  offset,
  onOffsetChange,
  readOnly,
}: {
  activity: ActivityMaster;
  config: import("../types").ActivityAccessConfig;
  offset: number;
  onOffsetChange: (offset: number) => void;
  readOnly: boolean;
}) {
  const [selected, setSelected] = React.useState<EmployeeSearchResult[]>([]);
  const grant = useGrantAccess(activity.id);
  const changeType = useChangeAccessType(activity.id);

  async function grantAccess() {
    try {
      await grant.mutateAsync(selected.map((e) => e.id));
      toast.success("Access granted");
      setSelected([]);
      onOffsetChange(0);
    } catch (err) {
      // Keep the selection so the PM can retry after a transient failure.
      toast.error(err instanceof AppError ? err.message : "Could not grant access.");
    }
  }

  async function makeCommon() {
    try {
      await changeType.mutateAsync({ access_type: "COMMON" });
      toast.success(`"${activity.name}" is now common`);
      onOffsetChange(0);
    } catch (err) {
      toast.error(err instanceof AppError ? err.message : "Could not make common.");
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 rounded-md border border-warning/30 bg-warning/5 p-3">
        <Lock className="h-4 w-4 text-warning" />
        <p className="flex-1 text-sm">
          <span className="font-medium">Restricted</span> - {config.authorized_count}{" "}
          employee{config.authorized_count === 1 ? "" : "s"} authorized.
        </p>
        <AlertDialog>
          <AlertDialogTrigger asChild>
            <Button size="sm" variant="secondary" disabled={readOnly}>
              Make common
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Make this activity common?</AlertDialogTitle>
              <AlertDialogDescription>
                All active employees will be able to select this activity. Current
                restricted-access assignments will be revoked. Existing reports will not
                be affected.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction onClick={() => void makeCommon()}>
                Make common
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>

      {!readOnly && (
        <div className="space-y-3 rounded-md border border-border p-3">
          <h5 className="text-sm font-medium">Grant access</h5>
          <EmployeeAccessSearch
            activityId={activity.id}
            selected={selected}
            onChange={setSelected}
          />
          <div className="flex justify-end">
            <Button
              size="sm"
              loading={grant.isPending}
              disabled={selected.length === 0}
              onClick={() => void grantAccess()}
            >
              Grant access
              {selected.length > 0 ? ` (${selected.length})` : ""}
            </Button>
          </div>
        </div>
      )}

      <AuthorizedEmployeesTable
        activityId={activity.id}
        config={config}
        offset={offset}
        onOffsetChange={onOffsetChange}
        disabled={readOnly}
      />
    </div>
  );
}
