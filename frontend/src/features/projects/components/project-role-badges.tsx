import * as React from "react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

/**
 * Effective project-role badges — the single source of truth for role colours,
 * labels, and ordering across the app. Every badge reuses the shared <Badge>
 * geometry but flattens it into a compact, professional SaaS-style chip
 * (GitHub / Linear / shadcn): a subtle border, light tint, semi-bold text and a
 * small colour dot — the emphasis comes from typography, not a bright pill. All
 * roles share one soft-tint formula and differ ONLY in hue:
 *   border-{c}-200 · bg-{c}-50 · text-{c}-700 · dot bg-{c}-500
 *
 *   Head → amber · Lead → blue · Contributor → gray · QC → purple
 *
 * Head is a project-level role; Lead / Contributor / QC are activity-level roles
 * that arrive in Phase 3. Rendering is fully generic — a caller (including the
 * future Phase 3 activity view) just passes the roles a person effectively holds
 * and the badges render in canonical order automatically:
 *
 *   <ProjectRoleBadges roles={[{ role: "head" }]} />
 */
export type ProjectRoleKey = "head" | "lead" | "contributor" | "qc";

/** Canonical render order — Head is always first. */
const ROLE_ORDER: ProjectRoleKey[] = ["head", "lead", "contributor", "qc"];

/** Flatten the shared <Badge> pill into a compact shadcn-style chip. twMerge
 * lets these win over the Badge base (rounded-full / px-2 / gap-1.5 / medium). */
const CHIP_BASE = "rounded-md px-1.5 py-0.5 gap-1 font-semibold";

const ROLE_META: Record<ProjectRoleKey, { label: string; chip: string; dot: string }> = {
  head: { label: "Head", chip: "border-amber-200 bg-amber-50 text-amber-700", dot: "bg-amber-500" },
  lead: { label: "Lead", chip: "border-blue-200 bg-blue-50 text-blue-700", dot: "bg-blue-500" },
  contributor: {
    label: "Contributor",
    chip: "border-gray-200 bg-gray-50 text-gray-700",
    dot: "bg-gray-400",
  },
  qc: { label: "QC", chip: "border-purple-200 bg-purple-50 text-purple-700", dot: "bg-purple-500" },
};

export function ProjectRoleBadges({
  roles,
  className,
}: {
  /** The roles a person effectively holds; order/duplicates don't matter. */
  roles: { role: ProjectRoleKey }[];
  className?: string;
}) {
  const present = new Set(roles.map((r) => r.role));
  const ordered = ROLE_ORDER.filter((r) => present.has(r));
  if (ordered.length === 0) return null;

  return (
    <div className={className ?? "mt-1 flex flex-wrap items-center gap-1.5"}>
      {ordered.map((r) => {
        const meta = ROLE_META[r];
        return (
          // Shared <Badge>; className flattens the geometry and sets the hue.
          <Badge key={r} className={cn(CHIP_BASE, meta.chip)}>
            <span className={cn("h-1.5 w-1.5 rounded-full", meta.dot)} aria-hidden />
            {meta.label}
          </Badge>
        );
      })}
    </div>
  );
}
