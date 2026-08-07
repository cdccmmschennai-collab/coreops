"use client";

import { Tags } from "lucide-react";

import { EmptyState } from "@/components/feedback/empty-state";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

import { tagScopePlaceholder, type ProjectScopeType } from "../scope";

/**
 * Tag Scope tab — still a placeholder.
 *
 * Phase 2 gave it one job: tell the PM / Head whether this project is
 * classified as tag-based, and where to change that. There is deliberately no
 * tag-count input, no scope form and no "Enable Tag Scope" button — the
 * classification is edited on the existing Project Edit page, so this tab adds
 * no second place to manage it. Visibility (PM / Head only) is decided upstream
 * by `features/projects/tabs.ts`; the copy comes from the pure
 * `tagScopePlaceholder` helper so it can be unit tested.
 */
export function TagScopeTab({ scopeType }: { scopeType: ProjectScopeType }) {
  const { title, description } = tagScopePlaceholder(scopeType);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Tag Scope</CardTitle>
      </CardHeader>
      <CardContent>
        <EmptyState icon={Tags} title={title} description={description} />
      </CardContent>
    </Card>
  );
}
