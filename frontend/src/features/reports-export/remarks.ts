// Day Remarks rendering for the PM Weekly Activity Report preview.
//
// The backend combines a split-day report's two half-remarks into one string,
// labelled and ordered "First Half: …\nSecond Half: …" (see
// work_reports.service.format_report_remarks). The single Remarks column renders
// each newline-separated segment on its own visible line — this helper turns the
// combined string into those lines. Full-day remarks pass through as a single
// line (or their own internal newlines). Blank/nullish -> no lines (empty cell).

export function remarkLines(remarks: string | null | undefined): string[] {
  if (!remarks) return [];
  return remarks.split("\n");
}
