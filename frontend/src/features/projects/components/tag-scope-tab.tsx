"use client";

import { Tags } from "lucide-react";

import { EmptyState } from "@/components/feedback/empty-state";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

/**
 * Phase 1 placeholder for the Project Tag Scope tab.
 *
 * Intentionally has no data fetching, no props and no business logic — the
 * scope fields, counts, revisions and APIs land in a later phase. Visibility is
 * decided upstream by `features/projects/tabs.ts` (PM / Head only).
 */
export function TagScopeTab() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Tag Scope</CardTitle>
      </CardHeader>
      <CardContent>
        <EmptyState
          icon={Tags}
          title="Tag scope not configured yet"
          description="Project tag scope configuration will be available here."
        />
      </CardContent>
    </Card>
  );
}
