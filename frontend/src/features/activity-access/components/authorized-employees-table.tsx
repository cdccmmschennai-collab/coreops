"use client";

import * as React from "react";
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
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { AppError } from "@/lib/api-client";

import { useRevokeAccess } from "../hooks";
import type { ActivityAccessConfig } from "../types";

function formatDate(iso: string | null): string {
  if (!iso) return "-";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "-" : d.toLocaleDateString();
}

export function AuthorizedEmployeesTable({
  activityId,
  config,
  offset,
  onOffsetChange,
  disabled,
}: {
  activityId: string;
  config: ActivityAccessConfig;
  offset: number;
  onOffsetChange: (offset: number) => void;
  disabled?: boolean;
}) {
  const revoke = useRevokeAccess(activityId);
  const { items, total, limit } = config;

  async function handleRevoke(employeeId: string, name: string) {
    try {
      await revoke.mutateAsync(employeeId);
      toast.success(`Access revoked for ${name}`);
    } catch (err) {
      toast.error(err instanceof AppError ? err.message : "Could not revoke access.");
    }
  }

  const from = total === 0 ? 0 : offset + 1;
  const to = Math.min(offset + limit, total);

  return (
    <div className="space-y-3">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Employee</TableHead>
            <TableHead className="w-28">Code</TableHead>
            <TableHead className="w-40">Granted by</TableHead>
            <TableHead className="w-32">Granted on</TableHead>
            <TableHead className="w-20" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.length === 0 && (
            <TableRow>
              <TableCell colSpan={5} className="text-center text-muted-foreground">
                No employees have access yet.
              </TableCell>
            </TableRow>
          )}
          {items.map((e) => (
            <TableRow key={e.employee_id}>
              <TableCell className="font-medium">{e.employee_name}</TableCell>
              <TableCell className="font-mono text-sm">{e.employee_code}</TableCell>
              <TableCell className="text-sm text-muted-foreground">
                {e.granted_by ?? "-"}
              </TableCell>
              <TableCell className="text-sm text-muted-foreground">
                {formatDate(e.granted_at)}
              </TableCell>
              <TableCell>
                <div className="flex justify-end">
                  <AlertDialog>
                    <AlertDialogTrigger asChild>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-destructive hover:text-destructive"
                        disabled={disabled || revoke.isPending}
                      >
                        Revoke
                      </Button>
                    </AlertDialogTrigger>
                    <AlertDialogContent>
                      <AlertDialogHeader>
                        <AlertDialogTitle>Revoke access?</AlertDialogTitle>
                        <AlertDialogDescription>
                          {e.employee_name} will no longer be able to select this
                          activity for new work. Existing reports are not affected.
                        </AlertDialogDescription>
                      </AlertDialogHeader>
                      <AlertDialogFooter>
                        <AlertDialogCancel>Cancel</AlertDialogCancel>
                        <AlertDialogAction
                          onClick={() => void handleRevoke(e.employee_id, e.employee_name)}
                        >
                          Revoke
                        </AlertDialogAction>
                      </AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>
                </div>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

      {total > limit && (
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <span>
            {from}-{to} of {total}
          </span>
          <div className="flex gap-2">
            <Button
              variant="secondary"
              size="sm"
              disabled={offset === 0}
              onClick={() => onOffsetChange(Math.max(0, offset - limit))}
            >
              Previous
            </Button>
            <Button
              variant="secondary"
              size="sm"
              disabled={to >= total}
              onClick={() => onOffsetChange(offset + limit)}
            >
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
