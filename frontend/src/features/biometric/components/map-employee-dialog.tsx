"use client";

import * as React from "react";
import { Check, Search } from "lucide-react";
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
import { AppError } from "@/lib/api-client";
import { cn } from "@/lib/utils";

import { useCreateMapping, useEmployeeSearch } from "../hooks";
import { employeeLabel, formatIST } from "../mapping-format";
import {
  PROVIDER_EASYTIME,
  type EmployeeOption,
  type ExternalCode,
} from "../types";

interface Choice {
  id: string;
  label: string;
}

/**
 * Confirm one EasyTime code -> CoreOps employee pairing.
 *
 * Nothing is pre-selected for an UNMAPPED code: the PM searches and picks. No
 * suggestion, no normalization rule, no name comparison decides anything here.
 * Re-opening a code that is already mapped shows its current employee, so
 * "Change" starts from the truth rather than from blank.
 *
 * The employee list is searched SERVER-side and restricted to active employees,
 * so the picker can never offer a deactivated record and never ships the full
 * directory to the browser.
 */
export function MapEmployeeDialog({
  row,
  open,
  onOpenChange,
}: {
  row: ExternalCode | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [choice, setChoice] = React.useState<Choice | null>(null);
  const [raw, setRaw] = React.useState("");
  const [debounced, setDebounced] = React.useState("");
  const createMapping = useCreateMapping();

  React.useEffect(() => {
    const t = setTimeout(() => setDebounced(raw.trim()), 300);
    return () => clearTimeout(t);
  }, [raw]);

  const query = useEmployeeSearch(debounced, open);

  // Reset per row: the previous row's choice must never leak into this one.
  React.useEffect(() => {
    if (!open || !row) return;
    setRaw("");
    setDebounced("");
    if (row.employee_id) {
      setChoice({
        id: row.employee_id,
        label: employeeLabel(row.employee_code, row.employee_name),
      });
    } else {
      setChoice(null);
    }
  }, [open, row]);

  if (!row) return null;

  const isRemap = row.status === "mapped";
  const results = query.data?.items ?? [];

  function pick(e: EmployeeOption) {
    setChoice({
      id: e.id,
      label: employeeLabel(e.employee_code, `${e.first_name} ${e.last_name}`.trim()),
    });
  }

  async function save() {
    if (!row || !choice) return;
    try {
      await createMapping.mutateAsync({
        provider: PROVIDER_EASYTIME,
        external_employee_code: row.external_employee_code,
        employee_id: choice.id,
      });
      toast.success(`EasyTime ${row.external_employee_code} mapped to ${choice.label}`);
      onOpenChange(false);
    } catch (err) {
      toast.error(
        err instanceof AppError ? err.message : "Could not save the mapping.",
      );
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>
            {isRemap ? "Change mapping" : "Map"} EasyTime{" "}
            <span className="font-mono">{row.external_employee_code}</span>
          </DialogTitle>
          <p className="text-sm text-muted-foreground">
            {row.punch_count} punch{row.punch_count === 1 ? "" : "es"} recorded,{" "}
            {formatIST(row.first_seen)} to {formatIST(row.last_seen)} IST.
          </p>
        </DialogHeader>

        <div className="space-y-4">
          {isRemap && (
            <div className="rounded-md border border-border bg-muted/30 p-3 text-sm">
              <p className="text-xs uppercase tracking-wide text-muted-foreground">
                Currently mapped to
              </p>
              <p className="font-medium">
                {employeeLabel(row.employee_code, row.employee_name)}
              </p>
            </div>
          )}

          <div className="space-y-2">
            <p className="text-sm font-medium">CoreOps employee</p>

            {choice && (
              <div className="flex items-center justify-between gap-2 rounded-md border border-primary/30 bg-primary/5 px-3 py-2 text-sm">
                <span className="font-medium">{choice.label}</span>
                <Check className="h-4 w-4 shrink-0 text-primary" aria-hidden />
              </div>
            )}

            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={raw}
                onChange={(e) => setRaw(e.target.value)}
                placeholder="Search by employee code or name…"
                className="pl-8"
                aria-label="Search employees"
              />
            </div>

            <div className="max-h-52 overflow-y-auto rounded-md border border-border">
              {query.isLoading && (
                <p className="p-2.5 text-sm text-muted-foreground">Searching…</p>
              )}
              {query.isError && (
                <p className="p-2.5 text-sm text-destructive">
                  Could not load employees.
                </p>
              )}
              {!query.isLoading && !query.isError && results.length === 0 && (
                <p className="p-2.5 text-sm text-muted-foreground">
                  No matching active employee.
                </p>
              )}
              {results.map((e) => (
                <button
                  key={e.id}
                  type="button"
                  onClick={() => pick(e)}
                  className={cn(
                    "flex w-full items-center justify-between gap-2 border-b border-border px-3 py-2 text-left text-sm last:border-b-0 hover:bg-accent/50",
                    choice?.id === e.id && "bg-accent/40",
                  )}
                >
                  <span>
                    <span className="font-mono text-xs text-muted-foreground">
                      {e.employee_code}
                    </span>
                    <span className="ml-2 font-medium">
                      {`${e.first_name} ${e.last_name}`.trim()}
                    </span>
                  </span>
                  {choice?.id === e.id && (
                    <Check className="h-4 w-4 shrink-0 text-primary" aria-hidden />
                  )}
                </button>
              ))}
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={() => void save()}
            disabled={!choice || choice.id === row.employee_id}
            loading={createMapping.isPending}
          >
            Save mapping
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
