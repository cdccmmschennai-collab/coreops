import { ArrowDown, ArrowUp } from "lucide-react";

import { cn } from "@/lib/utils";

export interface KpiProps {
  label: string;
  value: string;
  delta?: { dir: "up" | "down"; text: string };
  /** Optional control rendered inline with the value, right-aligned on the
   *  same row — for a tile that is also an entry point, e.g. Permission
   *  Remaining's Request button. Omitted by every other tile, which renders
   *  exactly as before (the value alone fills the row). */
  action?: React.ReactNode;
  /** Optional quiet line under the value — only for something the reader must
   *  act on, in practice "we couldn't load this". NOT for explaining a normal
   *  state: a tile that is simply showing a past month, or has no figure to
   *  show, says so with its label and its value. It is the one thing allowed to
   *  make the tile taller than its 80px floor, which is why it is reserved for
   *  a failure rather than spent on an ordinary state. */
  hint?: React.ReactNode;
}

/**
 * KPI tile — label, big tabular value, optional inline action.
 *
 * THE TILE IS 80px TALL - the height it has always been, which is exactly
 * `p-4` + the label line + `mt-1` + the 28px value. It is a FLOOR (`min-h-20`),
 * not a fixed height: the ordinary tile, with or without an action button, is
 * that 80px and nothing else, and only the error hint - a state the reader is
 * meant to notice - is allowed to add a line. Because the tiles are grid items
 * they stretch together, so that one hint never leaves a single card taller
 * than the three beside it.
 *
 * A hardcoded `h-[104px]` used to sit here, reserving a footnote slot in every
 * tile whether or not it had a footnote. That is what made the row visibly
 * bigger than the design; the slot is now taken only when something occupies
 * it. The value row still takes the slack (`flex-1`).
 *
 * The label is one line, truncated with the full text in a tooltip. A two-line
 * label was the other thing that made the row jump, and "Available Leave ·
 * Aug 2026" is exactly the kind of label that wraps in a narrow column.
 */
export function Kpi({ label, value, delta, action, hint }: KpiProps) {
  return (
    <div className="flex min-h-20 flex-col overflow-hidden rounded-lg border border-border bg-card p-4">
      <div className="truncate text-xs text-muted-foreground" title={label}>
        {label}
      </div>
      <div className="mt-1 flex flex-1 items-center justify-between gap-2">
        <div className="whitespace-nowrap text-[28px] font-semibold leading-none tracking-tight tabular">
          {value}
        </div>
        {action}
      </div>
      {delta && (
        <div
          className={cn(
            "mt-1.5 inline-flex items-center gap-1 text-xs",
            delta.dir === "up" ? "text-success" : "text-destructive",
          )}
        >
          {delta.dir === "up" ? (
            <ArrowUp className="h-3 w-3" />
          ) : (
            <ArrowDown className="h-3 w-3" />
          )}
          {delta.text}
        </div>
      )}
      {hint && (
        <div className="truncate text-[11px] text-muted-foreground">{hint}</div>
      )}
    </div>
  );
}

export function KpiGrid({ children }: { children: React.ReactNode }) {
  return <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">{children}</div>;
}
