import type { WorkReport } from "./types";

/**
 * Compact display of the distinct projects a report's activities touched.
 * - 0 projects → "—"
 * - 1 project  → the project name
 * - N projects → "First name +(N-1)", with the full list in `title` (tooltip)
 */
export function projectSummary(report: Pick<WorkReport, "tasks">): {
  label: string;
  title: string;
} {
  const names = [
    ...new Set(report.tasks.map((t) => t.project_name).filter((n): n is string => !!n)),
  ];
  if (names.length === 0) return { label: "—", title: "" };
  if (names.length === 1) return { label: names[0], title: names[0] };
  return { label: `${names[0]} +${names.length - 1}`, title: names.join(", ") };
}
