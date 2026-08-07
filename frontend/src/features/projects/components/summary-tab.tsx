"use client";

import { BarChart3 } from "lucide-react";

import { EmptyState } from "@/components/feedback/empty-state";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

/**
 * Phase 1 placeholder for the Project Summary tab.
 *
 * No calculations here by design — tag counts, employees worked, activity
 * progress, work days, person-days and completion percentages are later phases.
 * Visible to every user already permitted to view the project.
 */
export function SummaryTab() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Summary</CardTitle>
      </CardHeader>
      <CardContent>
        <EmptyState
          icon={BarChart3}
          title="Summary not available yet"
          description="Project work summary will be available here."
        />
      </CardContent>
    </Card>
  );
}
