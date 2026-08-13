"use client";

import * as React from "react";
import { Link2, Search, Unlink } from "lucide-react";
import { toast } from "sonner";

import { ErrorState } from "@/components/feedback/error-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs } from "@/components/ui/tabs";
import { AppError } from "@/lib/api-client";

import { useDeactivateMapping, useExternalCodes } from "../hooks";
import { employeeLabel, formatISTDate } from "../mapping-format";
import { PROVIDER_EASYTIME, type ExternalCode } from "../types";
import { MapEmployeeDialog } from "./map-employee-dialog";

const PAGE_SIZE = 50;

const FILTERS = [
  { value: "all", label: "All" },
  { value: "mapped", label: "Mapped" },
  { value: "unmapped", label: "Unmapped" },
];

/**
 * PM-only biometric employee mapping.
 *
 * Lists the EasyTime codes the devices ACTUALLY reported (read straight from
 * the raw punch log) next to the CoreOps employee each one resolves to, and
 * lets a project manager confirm, change or deactivate that pairing.
 *
 * Two things this screen deliberately does not do:
 *   - it proposes nobody. No suggested employee, no code normalization, no name
 *     matching: the PM reads the code and picks the person. Mapping is one code
 *     at a time, so no batch action can commit a pairing nobody looked at.
 *   - it never touches a punch. Mapping a code today makes its OLD punches
 *     attributable through the mapping table; the stored rows stay as they are.
 */
export function BiometricMappingTab() {
  const [filter, setFilter] = React.useState("all");
  const [raw, setRaw] = React.useState("");
  const [q, setQ] = React.useState("");
  const [page, setPage] = React.useState(0);
  const [editing, setEditing] = React.useState<ExternalCode | null>(null);

  React.useEffect(() => {
    const t = setTimeout(() => {
      setQ(raw.trim());
      setPage(0);
    }, 300);
    return () => clearTimeout(t);
  }, [raw]);

  const query = useExternalCodes({
    provider: PROVIDER_EASYTIME,
    status: filter,
    q,
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
  });
  const deactivate = useDeactivateMapping();

  const rows = query.data?.items ?? [];

  async function removeMapping(row: ExternalCode) {
    if (!row.mapping_id) return;
    try {
      await deactivate.mutateAsync(row.mapping_id);
      toast.success(`Mapping for ${row.external_employee_code} deactivated`);
    } catch (err) {
      toast.error(
        err instanceof AppError ? err.message : "Could not deactivate the mapping.",
      );
    }
  }

  const total = query.data?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-4 text-sm">
        <span className="text-muted-foreground">
          <span className="font-medium text-foreground">
            {query.data?.mapped_codes ?? 0}
          </span>{" "}
          of {query.data?.total_codes ?? 0} EasyTime codes mapped
        </span>
        {(query.data?.unmapped_codes ?? 0) > 0 && (
          <Badge variant="warning" dot>
            {query.data?.unmapped_codes} unmapped
          </Badge>
        )}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <Tabs
          items={FILTERS}
          value={filter}
          onChange={(next) => {
            setFilter(next);
            setPage(0);
          }}
        />
        <div className="relative w-full sm:w-72">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={raw}
            onChange={(e) => setRaw(e.target.value)}
            placeholder="Search code, employee code or name…"
            className="pl-8"
            aria-label="Search EasyTime codes"
          />
        </div>
      </div>

      {query.isLoading ? (
        <Card>
          <CardContent className="space-y-2 p-4">
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-5/6" />
            <Skeleton className="h-8 w-3/4" />
          </CardContent>
        </Card>
      ) : query.isError ? (
        <Card>
          <CardContent className="p-0">
            <ErrorState
              title="Could not load EasyTime codes"
              message="Please try again."
              onRetry={() => void query.refetch()}
            />
          </CardContent>
        </Card>
      ) : rows.length === 0 ? (
        <Card>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              {q || filter !== "all"
                ? "No EasyTime code matches this filter."
                : "No biometric punches have been received yet."}
            </p>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="overflow-x-auto p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>EasyTime code</TableHead>
                  <TableHead className="text-right">Punches</TableHead>
                  <TableHead>First seen</TableHead>
                  <TableHead>Last seen</TableHead>
                  <TableHead>Mapped employee</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((row) => (
                  <TableRow key={row.external_employee_code}>
                    <TableCell className="font-mono font-medium">
                      {row.external_employee_code}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {row.punch_count}
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-muted-foreground">
                      {formatISTDate(row.first_seen)}
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-muted-foreground">
                      {formatISTDate(row.last_seen)}
                    </TableCell>
                    <TableCell>
                      {row.employee_id
                        ? employeeLabel(row.employee_code, row.employee_name)
                        : "-"}
                    </TableCell>
                    <TableCell>
                      <StatusCell row={row} />
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-1">
                        <Button
                          size="sm"
                          variant={row.status === "mapped" ? "ghost" : "secondary"}
                          onClick={() => setEditing(row)}
                        >
                          <Link2 className="h-3.5 w-3.5" />
                          {row.status === "mapped" ? "Change" : "Map"}
                        </Button>
                        {row.status === "mapped" && (
                          <Button
                            size="sm"
                            variant="ghost"
                            loading={
                              deactivate.isPending &&
                              deactivate.variables === row.mapping_id
                            }
                            onClick={() => void removeMapping(row)}
                          >
                            <Unlink className="h-3.5 w-3.5 text-destructive" />
                            Deactivate
                          </Button>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {pageCount > 1 && (
        <div className="flex items-center justify-end gap-2 text-sm">
          <span className="text-muted-foreground">
            Page {page + 1} of {pageCount}
          </span>
          <Button
            size="sm"
            variant="secondary"
            disabled={page === 0}
            onClick={() => setPage((p) => Math.max(0, p - 1))}
          >
            Previous
          </Button>
          <Button
            size="sm"
            variant="secondary"
            disabled={page + 1 >= pageCount}
            onClick={() => setPage((p) => p + 1)}
          >
            Next
          </Button>
        </div>
      )}

      <MapEmployeeDialog
        row={editing}
        open={editing !== null}
        onOpenChange={(open) => {
          if (!open) setEditing(null);
        }}
      />
    </div>
  );
}

function StatusCell({ row }: { row: ExternalCode }) {
  if (row.status === "mapped") {
    return (
      <Badge variant="success" dot>
        Mapped
      </Badge>
    );
  }
  if (row.resolves_by_exact_code) {
    // No mapping row, but ingestion resolves this code by exact match anyway -
    // saying "unmapped" alone would be misleading.
    return (
      <Badge variant="info" dot>
        Exact code match
      </Badge>
    );
  }
  return (
    <Badge variant="warning" dot>
      Unmapped
    </Badge>
  );
}
