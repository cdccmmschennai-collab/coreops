"use client";

import * as React from "react";
import Link from "next/link";
import { Tags } from "lucide-react";

import { EmptyState } from "@/components/feedback/empty-state";
import { ErrorState } from "@/components/feedback/error-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { AppError } from "@/lib/api-client";
import { formatDateTime } from "@/lib/format";

import { useTagScope } from "../hooks";
import {
  buildTagScopeHistoryRows,
  buildTagScopeView,
  resolveScopeType,
  tagScopeActionLabel,
  tagScopeErrorMessage,
  TAG_SCOPE_STATUS_LABEL,
  type ProjectScopeType,
} from "../scope";
import { TagScopeDialog } from "./tag-scope-dialog";

interface TagScopeTabProps {
  projectId: string;
  /** From the project row the page already loaded — decides which state to show
   *  before the scope request resolves. */
  scopeType: ProjectScopeType;
  /** PM or this project's Head. Everyone who can view the project reaches this
   *  tab, so this is the only thing separating a reader from an editor here —
   *  it gates the Set / Revise and Edit Project actions. The API enforces the
   *  same rule on the write endpoint, so hiding the button is convenience, not
   *  the control. */
  canEdit: boolean;
}

/**
 * "Initial Estimate" reads as not settled yet, "Confirmed Scope" as accepted.
 *
 * `status` arrives already translated (both callers take it from a row the
 * scope module built), so the comparison goes through TAG_SCOPE_STATUS_LABEL
 * instead of a literal — renaming a label must not silently change a colour.
 */
function StatusBadge({ status }: { status: string }) {
  const settled = status === TAG_SCOPE_STATUS_LABEL.BASELINED;
  return (
    <Badge variant={settled ? "success" : "warning"} dot>
      {status}
    </Badge>
  );
}

/** Newest revision first — the current scope is the answer, the trail is context. */
function ScopeHistory({ rows }: { rows: ReturnType<typeof buildTagScopeHistoryRows> }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Scope History</CardTitle>
      </CardHeader>
      <CardContent className="px-0 pb-0">
        {rows.length === 0 ? (
          <p className="px-6 pb-6 text-sm text-muted-foreground">
            No revisions recorded yet.
          </p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="text-right">Revision</TableHead>
                <TableHead className="text-right">Previous</TableHead>
                <TableHead className="text-right">New</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Reason</TableHead>
                <TableHead>Updated By</TableHead>
                <TableHead>Date</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((r) => (
                <TableRow key={r.key}>
                  <TableCell className="text-right font-medium tabular">
                    {r.revision}
                  </TableCell>
                  <TableCell className="text-right tabular text-muted-foreground">
                    {r.previous}
                  </TableCell>
                  <TableCell className="text-right font-medium tabular">{r.next}</TableCell>
                  <TableCell>
                    <StatusBadge status={r.status} />
                  </TableCell>
                  <TableCell className="max-w-xs whitespace-pre-wrap">{r.reason}</TableCell>
                  <TableCell className="whitespace-nowrap">{r.updatedBy}</TableCell>
                  <TableCell className="whitespace-nowrap text-muted-foreground">
                    {r.date}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}

/**
 * Tag Scope tab — the administrative screen for a project's estimated tag
 * scope: what it is now, how it got there, and the controlled way to change it.
 *
 * Readable by every project viewer: the scope and the reasons it changed are
 * context contributors need. Only the actions are restricted (see `canEdit`).
 *
 * Current scope comes from GET /projects/{id}/tag-scope rather than the project
 * row, because that response also carries the revision history and the resolved
 * author name, and because a write returns the identical payload — so saving
 * refreshes everything on screen without a second request or a page reload.
 *
 * Still no progress, worked-tag or remaining figure: those need Daily Report
 * data that no phase up to this one touches.
 */
export function TagScopeTab({ projectId, scopeType, canEdit }: TagScopeTabProps) {
  const [dialogOpen, setDialogOpen] = React.useState(false);
  const isTagBased = scopeType === "TAG_BASED";
  // A non-tag project has nothing to fetch: no estimate, no history, and never
  // will while it stays NONE.
  const query = useTagScope(projectId, isTagBased);

  if (!isTagBased) {
    const view = buildTagScopeView({
      scopeType,
      estimatedTagCount: null,
      tagScopeStatus: null,
      tagScopeRevision: 0,
    });
    return (
      <Card>
        <CardHeader>
          <CardTitle>Tag Scope</CardTitle>
        </CardHeader>
        <CardContent>
          <EmptyState
            icon={Tags}
            title={view.message}
            description={view.hint}
            action={
              canEdit ? (
                <Button variant="secondary" asChild>
                  <Link href={`/projects/${projectId}/edit`}>Edit Project</Link>
                </Button>
              ) : undefined
            }
          />
        </CardContent>
      </Card>
    );
  }

  if (query.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-64" />
        <Skeleton className="h-40" />
      </div>
    );
  }

  if (query.isError || !query.data) {
    const status = query.error instanceof AppError ? query.error.status : null;
    const message = query.error instanceof AppError ? query.error.message : null;
    return (
      <Card>
        <CardHeader>
          <CardTitle>Tag Scope</CardTitle>
        </CardHeader>
        <CardContent>
          <ErrorState
            title="Couldn't load tag scope"
            message={tagScopeErrorMessage(status, message)}
            // A 403/404 will not resolve by retrying; anything else might.
            onRetry={
              status === 403 || status === 404 ? undefined : () => void query.refetch()
            }
          />
        </CardContent>
      </Card>
    );
  }

  const scope = query.data;
  const view = buildTagScopeView({
    // The response is authoritative — it is what the last write returned.
    scopeType: resolveScopeType(scope.scope_type),
    estimatedTagCount: scope.estimated_tag_count,
    tagScopeStatus: scope.tag_scope_status,
    tagScopeRevision: scope.tag_scope_revision,
    updatedAt: scope.tag_scope_updated_at ? formatDateTime(scope.tag_scope_updated_at) : null,
    updatedByName: scope.tag_scope_updated_by_name,
  });
  const historyRows = buildTagScopeHistoryRows(scope.revisions ?? [], formatDateTime);

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Project Tag Scope</CardTitle>
        </CardHeader>
        <CardContent>
          {view.message && (
            <div className="mb-2">
              <p className="text-sm font-medium text-foreground">{view.message}</p>
              {view.hint && (
                <p className="mt-0.5 text-sm text-muted-foreground">{view.hint}</p>
              )}
            </div>
          )}
          <dl className="divide-y divide-border">
            {view.rows.map((row) => (
              <div
                key={row.label}
                className="flex items-center justify-between gap-4 py-2 text-sm"
              >
                <dt className="text-muted-foreground">{row.label}</dt>
                <dd className="text-right font-medium tabular">
                  {row.label === "Status" && view.kind === "configured" ? (
                    <StatusBadge status={row.value} />
                  ) : (
                    row.value
                  )}
                </dd>
              </div>
            ))}
          </dl>
          {canEdit && (
            <div className="mt-4 flex justify-end">
              <Button onClick={() => setDialogOpen(true)}>
                {tagScopeActionLabel(view.kind)}
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Only once there is a trail to show — an empty table under a brand new
          project says nothing the panel above has not already said. */}
      {view.kind === "configured" && <ScopeHistory rows={historyRows} />}

      <TagScopeDialog
        projectId={projectId}
        estimatedTagCount={scope.estimated_tag_count ?? null}
        status={scope.tag_scope_status ?? null}
        revision={scope.tag_scope_revision}
        open={dialogOpen}
        onOpenChange={setDialogOpen}
      />
    </div>
  );
}
