"use client";

import * as React from "react";
import { Search, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { COUNT_FIELDS, COUNT_FIELD_LABEL, type RelevantCountField } from "@/features/activity-master/types";

import { buildGuideRows, resultCountLabel, type GuideRow } from "../filter";
import { type BenchmarkModeKey } from "../format";
import { useBenchmarkGuide } from "../hooks";

// Short labels — mirror the table's Mode column (see MODE_LABEL_SHORT in format.ts).
const MODE_FILTER_OPTIONS: { value: BenchmarkModeKey; label: string }[] = [
  { value: "numeric", label: "Numeric daily" },
  { value: "task_quantity", label: "Quantity + completion" },
  { value: "task_completion", label: "Completion only" },
];

const COLUMNS = [
  { key: "no", label: "SL.No", className: "w-14 text-right tabular" },
  { key: "activity", label: "Activity", className: "" },
  { key: "sub", label: "Sub-Activity", className: "" },
  { key: "benchmark", label: "Benchmark", className: "" },
  { key: "unit", label: "Unit / Period", className: "" },
  { key: "mode", label: "Mode", className: "" },
  { key: "remarks", label: "Remarks", className: "" },
] as const;

interface BenchmarkGuideDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function BenchmarkGuideDialog({ open, onOpenChange }: BenchmarkGuideDialogProps) {
  // Two independent search boxes (clearing one never touches the other) plus the
  // Unit / Mode dropdown filters.
  const [activitySearch, setActivitySearch] = React.useState("");
  const [subActivitySearch, setSubActivitySearch] = React.useState("");
  const [unit, setUnit] = React.useState<RelevantCountField | "all">("all");
  const [mode, setMode] = React.useState<BenchmarkModeKey | "all">("all");

  const query = useBenchmarkGuide(open);

  const rows = React.useMemo<GuideRow[]>(
    () => buildGuideRows(query.data ?? [], { activitySearch, subActivitySearch, unit, mode }),
    [query.data, activitySearch, subActivitySearch, unit, mode],
  );

  // total = authorized/active rows the API returned (pre local filtering);
  // visible = rows surviving the searches + Unit/Mode filters.
  const total = query.data?.length ?? 0;
  const hasAnyData = total > 0;

  const anyFilterActive =
    activitySearch !== "" || subActivitySearch !== "" || unit !== "all" || mode !== "all";

  // Reset all four controls to defaults — pure local state, no refetch (the
  // query key is unchanged so cached API data is reused) and no Activity Master
  // side effects. The dialog stays open.
  const clearFilters = React.useCallback(() => {
    setActivitySearch("");
    setSubActivitySearch("");
    setUnit("all");
    setMode("all");
  }, []);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[85vh] w-[95vw] max-w-[1200px] flex-col gap-0 overflow-hidden p-0 sm:w-[95vw]">
        {/* sticky header: title, subtitle, search + filters */}
        <div className="shrink-0 border-b border-border px-5 pb-4 pt-5">
          <DialogTitle>Benchmark Guide</DialogTitle>
          <p className="text-sm text-muted-foreground">
            Current activities, targets and completion rules
          </p>
          <div className="mt-3 flex flex-col gap-2 pr-8 sm:flex-row sm:items-center">
            <SearchBox
              value={activitySearch}
              onChange={setActivitySearch}
              label="Activity Search"
              placeholder="Search activity"
            />
            <SearchBox
              value={subActivitySearch}
              onChange={setSubActivitySearch}
              label="Sub-Activity Search"
              placeholder="Search sub-activity"
            />
            <Select value={unit} onValueChange={(v) => setUnit(v as RelevantCountField | "all")}>
              <SelectTrigger className="sm:w-36" aria-label="Filter by unit">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Unit: All</SelectItem>
                {COUNT_FIELDS.map((u) => (
                  <SelectItem key={u} value={u}>
                    {COUNT_FIELD_LABEL[u]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={mode} onValueChange={(v) => setMode(v as BenchmarkModeKey | "all")}>
              <SelectTrigger className="sm:w-52" aria-label="Filter by mode">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Mode: All</SelectItem>
                {MODE_FILTER_OPTIONS.map((m) => (
                  <SelectItem key={m.value} value={m.value}>
                    {m.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* quiet utility row: result count (left) + clear filters (right) */}
          {hasAnyData && (
            <div className="mt-2 flex min-h-6 items-center justify-between gap-3 pr-8">
              <p className="text-xs text-muted-foreground" aria-live="polite">
                {resultCountLabel(rows.length, total)}
              </p>
              {anyFilterActive && (
                <button
                  type="button"
                  onClick={clearFilters}
                  className="text-xs font-medium text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
                >
                  Clear filters
                </button>
              )}
            </div>
          )}
        </div>

        {/* scrollable table area */}
        <div className="flex-1 overflow-auto">
          {query.isLoading ? (
            <GuideSkeleton />
          ) : query.isError ? (
            <GuideMessage>
              <p>Unable to load the Benchmark Guide.</p>
              <Button
                variant="secondary"
                size="sm"
                className="mt-3"
                onClick={() => void query.refetch()}
              >
                Retry
              </Button>
            </GuideMessage>
          ) : !hasAnyData ? (
            <GuideMessage>No activities are currently available to your account.</GuideMessage>
          ) : rows.length === 0 ? (
            <GuideMessage>No matching activities or benchmarks found.</GuideMessage>
          ) : (
            <table className="w-full min-w-[720px] caption-bottom text-sm">
              <thead className="sticky top-0 z-10 bg-card">
                <tr className="border-b border-border">
                  {COLUMNS.map((c) => (
                    <th
                      key={c.key}
                      className={`h-10 px-3 text-left align-middle text-xs font-semibold uppercase tracking-wide text-muted-foreground ${c.className}`}
                    >
                      {c.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} className="border-b border-border last:border-0 hover:bg-secondary/50">
                    <td className="px-3 py-3 text-right align-top tabular text-muted-foreground">{r.no}</td>
                    <td className="px-3 py-3 align-top font-medium text-foreground">{r.activityName}</td>
                    <td className="px-3 py-3 align-top">{r.subActivityName}</td>
                    <td
                      className={
                        r.isNumeric
                          ? "px-3 py-3 align-top text-right tabular"
                          : "px-3 py-3 align-top text-left"
                      }
                    >
                      {r.benchmark}
                    </td>
                    <td className="px-3 py-3 align-top text-muted-foreground">{r.unitPeriod}</td>
                    <td className="px-3 py-3 align-top text-muted-foreground">
                      <span title={r.modeDescription} aria-label={r.modeDescription}>
                        {r.mode}
                      </span>
                    </td>
                    <td className="px-3 py-3 align-top text-muted-foreground">{r.remarks || "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

/** A labelled search input with a leading icon and an individual clear button.
 *  Each box is independent — clearing one leaves the other untouched. */
function SearchBox({
  value,
  onChange,
  label,
  placeholder,
}: {
  value: string;
  onChange: (v: string) => void;
  label: string;
  placeholder: string;
}) {
  return (
    <div className="relative flex-1">
      <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
      <Input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        aria-label={label}
        className="min-w-[10rem] px-9"
      />
      {value && (
        <button
          type="button"
          onClick={() => onChange("")}
          aria-label={`Clear ${label}`}
          className="absolute right-2 top-1/2 -translate-y-1/2 rounded-sm p-0.5 text-muted-foreground hover:text-foreground"
        >
          <X className="h-4 w-4" />
        </button>
      )}
    </div>
  );
}

function GuideMessage({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-16 text-center text-sm text-muted-foreground">
      {children}
    </div>
  );
}

function GuideSkeleton() {
  return (
    <div className="space-y-2 p-4" aria-hidden>
      {Array.from({ length: 8 }).map((_, i) => (
        <div key={i} className="h-9 w-full animate-pulse rounded-md bg-muted" />
      ))}
    </div>
  );
}
