"use client";

import { CalendarClock, GitMerge, UserMinus, UserPlus } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { AppError } from "@/lib/api-client";

import { useProjectTimeline } from "../hooks";
import type { ProjectTimelineEvent } from "../types";

// ── event formatting ──────────────────────────────────────────────────────────

type EventMeta = {
  icon: React.ReactNode;
  description: string;
};

function formatEvent(e: ProjectTimelineEvent): EventMeta {
  const d = e.details as Record<string, string | null>;

  switch (e.event_type) {
    case "project_created":
      return {
        icon: <GitMerge className="h-3.5 w-3.5" />,
        description: "Project created",
      };

    case "planned_date_changed": {
      const from = d.old_date ?? "—";
      const to = d.new_date ?? "—";
      const reason = d.reason ? ` · ${d.reason}` : "";
      return {
        icon: <CalendarClock className="h-3.5 w-3.5" />,
        description: `Planned completion changed ${from} → ${to}${reason}`,
      };
    }

    case "member_added":
      return {
        icon: <UserPlus className="h-3.5 w-3.5" />,
        description: `${d.employee_name ?? "Unknown"} added as ${d.role ?? "member"}`,
      };

    case "member_removed":
      return {
        icon: <UserMinus className="h-3.5 w-3.5" />,
        description: `${d.employee_name ?? "Unknown"} removed`,
      };

    case "submission_created":
      return {
        icon: <GitMerge className="h-3.5 w-3.5" />,
        description: `Submission created${d.period_start ? ` for ${d.period_start} – ${d.period_end ?? ""}` : ""}`,
      };

    case "submission_updated":
      return {
        icon: <GitMerge className="h-3.5 w-3.5" />,
        description: `Submission updated${d.field ? ` (${d.field}: ${d.old} → ${d.new})` : ""}`,
      };

    default:
      return {
        icon: <GitMerge className="h-3.5 w-3.5" />,
        description: e.event_type.replace(/_/g, " "),
      };
  }
}

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// ── component ─────────────────────────────────────────────────────────────────

export function ProjectTimeline({ projectId }: { projectId: string }) {
  const query = useProjectTimeline(projectId);
  const events = query.data ?? [];

  // Don't render for members who don't have timeline access (team_lead+PM only)
  if (query.isError && query.error instanceof AppError && query.error.status === 403) {
    return null;
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Timeline</CardTitle>
      </CardHeader>
      <CardContent>
        {query.isLoading && (
          <div className="space-y-3">
            {[1, 2, 3].map((n) => (
              <Skeleton key={n} className="h-10 w-full" />
            ))}
          </div>
        )}

        {!query.isLoading && events.length === 0 && (
          <p className="text-sm text-muted-foreground">No events recorded yet.</p>
        )}

        {!query.isLoading && events.length > 0 && (
          <ol className="relative border-l border-border">
            {events.map((e) => {
              const { icon, description } = formatEvent(e);
              return (
                <li key={e.id} className="mb-6 ml-4 last:mb-0">
                  <span className="absolute -left-[1.1rem] flex h-[1.4rem] w-[1.4rem] items-center justify-center rounded-full border border-border bg-card text-muted-foreground">
                    {icon}
                  </span>
                  <p className="text-sm font-medium">{description}</p>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    {e.actor_name ?? "System"} · {formatDateTime(e.created_at)}
                  </p>
                </li>
              );
            })}
          </ol>
        )}
      </CardContent>
    </Card>
  );
}
