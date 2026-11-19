"use client";

import * as React from "react";
import { ChevronDown, ChevronRight, PlusCircle, ShieldCheck, X } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { AppError } from "@/lib/api-client";
import { cn } from "@/lib/utils";

import { groupApprovalCandidates } from "../approval-activities";
import {
  useActivityMasterSearchIndex,
  useApprovalActivities,
  useSetApproval,
} from "../hooks";
import type { ApprovalActivity, SubActivityFlat } from "../types";

/**
 * Settings -> Activity Master -> Approval Activities (migration 0090).
 * Opened from the toolbar button beside the search; hidden by default so the
 * Activity Master listing looks exactly as before.
 *
 * The sub-activities whose report rows need PM approval once a report is
 * submitted. Strictly sub-activity level: the picker only ever adds one
 * sub-activity at a time, and a parent row is just a group header. "Rework" in
 * a name is a search hint (the "Rework only" filter), never automatic.
 */
/** Toolbar button beside the Activity Master search, with the configured count. */
export function ApprovalActivitiesButton({
  open,
  onToggle,
}: {
  open: boolean;
  onToggle: () => void;
}) {
  const list = useApprovalActivities();
  const count = list.data?.length ?? 0;
  return (
    <Button
      size="sm"
      variant="secondary"
      className={cn("shrink-0", open && "ring-2 ring-warning/40")}
      onClick={onToggle}
      aria-expanded={open}
    >
      <ShieldCheck className="h-4 w-4 text-warning" />
      <span className="hidden sm:inline">Approval Activities</span>
      <span className="sr-only sm:hidden">Approval Activities</span>
      {count > 0 && (
        <Badge variant="warning" className="ml-1">
          {count}
        </Badge>
      )}
    </Button>
  );
}

export function ApprovalActivitiesPanel({ onClose }: { onClose: () => void }) {
  const [adding, setAdding] = React.useState(false);
  const list = useApprovalActivities();
  const setApproval = useSetApproval();
  const [pendingId, setPendingId] = React.useState<string | null>(null);

  const configured = list.data ?? [];

  async function change(id: string, name: string, value: boolean) {
    setPendingId(id);
    try {
      await setApproval.mutateAsync({ id, value });
      toast.success(
        value ? `"${name}" now requires PM approval` : `"${name}" removed from Approval Activities`,
      );
    } catch (err) {
      toast.error(err instanceof AppError ? err.message : "Could not update the approval setting.");
    } finally {
      setPendingId(null);
    }
  }

  return (
    <Card className="p-0">
      <CardHeader className="flex-row items-center justify-between gap-3 space-y-0 border-b border-border px-4 py-3">
        <CardTitle className="flex min-w-0 items-center gap-2 text-base">
          <ShieldCheck className="h-4 w-4 text-warning" />
          Approval Activities
        </CardTitle>
        <div className="flex shrink-0 gap-2">
          {!adding && (
            <Button size="sm" variant="secondary" onClick={() => setAdding(true)}>
              <PlusCircle className="h-4 w-4" />
              Add Sub-Activity
            </Button>
          )}
          <Button
            size="icon"
            variant="ghost"
            className="h-8 w-8"
            onClick={onClose}
            aria-label="Close Approval Activities"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      </CardHeader>

      <CardContent className="space-y-4 p-4">
        {adding && (
          <CandidatePicker
            onClose={() => setAdding(false)}
            pendingId={pendingId}
            onAdd={(s) => void change(s.id, s.name, true)}
          />
        )}

        <ConfiguredTable
          rows={configured}
          loading={list.isLoading}
          error={list.isError}
          pendingId={pendingId}
          onRemove={(r) => void change(r.id, r.name, false)}
        />
      </CardContent>
    </Card>
  );
}

function ConfiguredTable({
  rows,
  loading,
  error,
  pendingId,
  onRemove,
}: {
  rows: ApprovalActivity[];
  loading: boolean;
  error: boolean;
  pendingId: string | null;
  onRemove: (r: ApprovalActivity) => void;
}) {
  return (
    <div className="overflow-x-auto rounded-md border border-border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Activity</TableHead>
            <TableHead>Sub-Activity</TableHead>
            <TableHead className="w-24 text-center">Status</TableHead>
            <TableHead className="w-24" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {loading && (
            <TableRow>
              <TableCell colSpan={4} className="text-center text-muted-foreground">
                Loading...
              </TableCell>
            </TableRow>
          )}
          {!loading && error && (
            <TableRow>
              <TableCell colSpan={4} className="text-center text-destructive">
                Could not load Approval Activities.
              </TableCell>
            </TableRow>
          )}
          {!loading && !error && rows.length === 0 && (
            <TableRow>
              <TableCell colSpan={4} className="text-center text-muted-foreground">
                No sub-activities require PM approval yet.
              </TableCell>
            </TableRow>
          )}
          {rows.map((r) => (
            <TableRow key={r.id} className={!r.is_active ? "opacity-60" : ""}>
              <TableCell className="text-sm text-muted-foreground">{r.activity_name}</TableCell>
              <TableCell className="font-medium">{r.name}</TableCell>
              <TableCell className="text-center">
                <Badge variant={r.is_active ? "success" : "neutral"} dot>
                  {r.is_active ? "Active" : "Inactive"}
                </Badge>
              </TableCell>
              <TableCell className="text-right">
                <Button
                  size="sm"
                  variant="ghost"
                  className="text-destructive hover:text-destructive"
                  disabled={pendingId === r.id}
                  onClick={() => onRemove(r)}
                >
                  <X className="h-3.5 w-3.5" />
                  Remove
                </Button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function CandidatePicker({
  onClose,
  onAdd,
  pendingId,
}: {
  onClose: () => void;
  onAdd: (s: SubActivityFlat) => void;
  pendingId: string | null;
}) {
  const [term, setTerm] = React.useState("");
  const [reworkOnly, setReworkOnly] = React.useState(true);
  const [toggled, setToggled] = React.useState<Record<string, boolean>>({});
  const index = useActivityMasterSearchIndex(true);

  const groups = React.useMemo(
    () => groupApprovalCandidates(index.data ?? [], term, { reworkOnly }),
    [index.data, term, reworkOnly],
  );
  // A search or the rework filter auto-expands every group; with neither, the
  // admin expands the parent they want by hand.
  const autoExpand = term.trim().length > 0 || reworkOnly;

  return (
    <div className="space-y-3 rounded-md border border-dashed border-border p-3">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <Input
          autoFocus
          placeholder="Search activities and sub-activities..."
          value={term}
          onChange={(e) => {
            setTerm(e.target.value);
            setToggled({});
          }}
          className="min-w-0 sm:flex-1"
          aria-label="Search sub-activities to add"
        />
        <div className="flex gap-2">
          <Button
            size="sm"
            variant={reworkOnly ? "secondary" : "ghost"}
            onClick={() => {
              setReworkOnly((v) => !v);
              setToggled({});
            }}
            aria-pressed={reworkOnly}
          >
            Rework only
          </Button>
          <Button size="sm" variant="ghost" onClick={onClose}>
            Done
          </Button>
        </div>
      </div>

      <div className="max-h-80 overflow-y-auto rounded-md border border-border">
        {index.isLoading ? (
          <p className="p-3 text-sm text-muted-foreground">Loading sub-activities...</p>
        ) : groups.length === 0 ? (
          <p className="p-3 text-sm text-muted-foreground">
            No sub-activities to add{reworkOnly ? ' - try turning off "Rework only"' : ""}.
          </p>
        ) : (
          groups.map((g) => {
            const expanded = toggled[g.activityId] ?? autoExpand;
            return (
              <div key={g.activityId} className="border-b border-border last:border-b-0">
                <button
                  type="button"
                  className="flex w-full items-center gap-2 bg-muted/30 px-3 py-2 text-left text-sm font-medium"
                  onClick={() => setToggled((prev) => ({ ...prev, [g.activityId]: !expanded }))}
                  aria-expanded={expanded}
                >
                  {expanded ? (
                    <ChevronDown className="h-3.5 w-3.5" />
                  ) : (
                    <ChevronRight className="h-3.5 w-3.5" />
                  )}
                  {g.activityName}
                  <span className="ml-auto text-xs font-normal text-muted-foreground">
                    {g.subs.length}
                  </span>
                </button>
                {expanded && (
                  <ul>
                    {g.subs.map((s) => (
                      <li
                        key={s.id}
                        className={cn(
                          "flex items-center gap-2 px-3 py-1.5 pl-9 text-sm",
                          !s.is_active && "opacity-60",
                        )}
                      >
                        <span className="min-w-0 flex-1 truncate">{s.name}</span>
                        {!s.is_active && <Badge variant="neutral">Inactive</Badge>}
                        <Button
                          size="sm"
                          variant="ghost"
                          disabled={pendingId === s.id}
                          onClick={() => onAdd(s)}
                        >
                          <PlusCircle className="h-3.5 w-3.5" />
                          Add
                        </Button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
