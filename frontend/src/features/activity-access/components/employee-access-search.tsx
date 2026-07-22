"use client";

import * as React from "react";
import { Check, Search, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

import { useEmployeeAccessSearch } from "../hooks";
import {
  canSearchEmployees,
  employeeLabel,
  EMPLOYEE_SEARCH_MIN_CHARS,
  type EmployeeSearchResult,
} from "../types";

/** Debounced, server-side employee multi-select. Controlled: the parent owns the
 *  selected list and the submit action (grant vs restrict). Search starts at 2
 *  characters, debounces ~300ms, caps at ~20 results, and never loads the full
 *  directory. Already-granted employees are excluded server-side. */
export function EmployeeAccessSearch({
  activityId,
  selected,
  onChange,
}: {
  activityId: string;
  selected: EmployeeSearchResult[];
  onChange: (next: EmployeeSearchResult[]) => void;
}) {
  const [raw, setRaw] = React.useState("");
  const [debounced, setDebounced] = React.useState("");

  React.useEffect(() => {
    const t = setTimeout(() => setDebounced(raw.trim()), 300);
    return () => clearTimeout(t);
  }, [raw]);

  const query = useEmployeeAccessSearch(activityId, debounced);
  const selectedIds = new Set(selected.map((e) => e.id));
  const results = (query.data?.items ?? []).filter((e) => !selectedIds.has(e.id));
  const canSearch = canSearchEmployees(debounced);
  const tooShort = debounced.length > 0 && !canSearch;

  function add(e: EmployeeSearchResult) {
    onChange([...selected, e]);
  }
  function remove(id: string) {
    onChange(selected.filter((e) => e.id !== id));
  }

  return (
    <div className="space-y-3">
      <div className="relative">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={raw}
          onChange={(e) => setRaw(e.target.value)}
          placeholder="Search employees by name or code…"
          className="pl-8"
          aria-label="Search employees"
        />
      </div>

      {selected.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {selected.map((e) => (
            <Badge key={e.id} variant="info" className="gap-1">
              {employeeLabel(e)} · {e.employee_code}
              <button
                type="button"
                onClick={() => remove(e.id)}
                aria-label={`Remove ${employeeLabel(e)}`}
                className="rounded-sm opacity-70 hover:opacity-100"
              >
                <X className="h-3 w-3" />
              </button>
            </Badge>
          ))}
        </div>
      )}

      {/* Results box only exists once the PM starts typing — the input
          placeholder already identifies the search, so no idle helper text. */}
      {debounced.length > 0 && (
        <div className="max-h-48 overflow-y-auto rounded-md border border-border">
          {tooShort && (
            <p className="p-2.5 text-sm text-muted-foreground">
              Type at least {EMPLOYEE_SEARCH_MIN_CHARS} characters.
            </p>
          )}
          {canSearch && query.isLoading && (
            <p className="p-2.5 text-sm text-muted-foreground">Searching…</p>
          )}
          {canSearch && query.isError && (
            <p className="p-2.5 text-sm text-destructive">Could not search employees.</p>
          )}
          {canSearch && !query.isLoading && !query.isError && results.length === 0 && (
            <p className="p-2.5 text-sm text-muted-foreground">No matching active employees.</p>
          )}
          {results.map((e) => (
            <button
              key={e.id}
              type="button"
              onClick={() => add(e)}
              className={cn(
                "flex w-full items-center justify-between gap-2 border-b border-border px-3 py-2 text-left text-sm last:border-b-0",
                "hover:bg-accent/50",
              )}
            >
              <span>
                <span className="font-medium">{employeeLabel(e)}</span>
                <span className="ml-2 font-mono text-xs text-muted-foreground">
                  {e.employee_code}
                </span>
              </span>
              <Check className="h-4 w-4 text-muted-foreground opacity-0" aria-hidden />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
