"use client";

import { Tags } from "lucide-react";

import { EmptyState } from "@/components/feedback/empty-state";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

import { buildTagScopeView, type TagScopeInput } from "../scope";

/**
 * Tag Scope tab — read-only view of the project's current tag scope.
 *
 * Phase 3 shows what the scope IS (estimate, status, revision) and nothing
 * more: no editing, no "Revise scope" action, and no progress / worked /
 * remaining figures — those need Daily Report data this phase does not touch.
 * The managed scope-change workflow is Phase 4.
 *
 * Values come from the project record the page already loaded, so opening the
 * tab costs no extra request. Visibility (PM or this project's Head) is decided
 * upstream by `features/projects/tabs.ts`, and the API enforces the same rule
 * on GET /projects/{id}/tag-scope.
 */
export function TagScopeTab(props: TagScopeInput) {
  const view = buildTagScopeView(props);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Tag Scope</CardTitle>
      </CardHeader>
      <CardContent>
        {view.kind === "not-tag-based" ? (
          <EmptyState icon={Tags} title={view.message} description={view.hint} />
        ) : (
          <div className="space-y-4">
            {view.message && (
              <div>
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
                  <dd className="text-right font-medium tabular">{row.value}</dd>
                </div>
              ))}
            </dl>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
