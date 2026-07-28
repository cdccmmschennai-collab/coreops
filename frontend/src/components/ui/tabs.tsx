"use client";

import { cn } from "@/lib/utils";

export interface TabItem {
  value: string;
  label: string;
  count?: number;
  /** Tint for the count pill when the tab is inactive. Omit for the default
   *  neutral pill; `warning`/`info` mark a queue that needs attention. */
  countVariant?: "warning" | "info";
}

const COUNT_TINT: Record<NonNullable<TabItem["countVariant"]>, string> = {
  warning: "bg-warning/15 text-warning",
  info: "bg-info/15 text-info",
};

/**
 * Lightweight underline tabs matching the design system (app.css `.tabs/.tab`).
 * Controlled: parent owns the active value. No extra deps.
 */
export function Tabs({
  items,
  value,
  onChange,
  className,
}: {
  items: TabItem[];
  value: string;
  onChange: (value: string) => void;
  className?: string;
}) {
  return (
    <div className={cn("flex gap-6 overflow-x-auto border-b border-border", className)} role="tablist">
      {items.map((it) => {
        const active = it.value === value;
        return (
          <button
            key={it.value}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(it.value)}
            className={cn(
              "-mb-px whitespace-nowrap border-b-2 py-2.5 text-sm font-medium transition-colors",
              active
                ? "border-primary text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            {it.label}
            {it.count !== undefined && (
              <span
                className={cn(
                  "ml-1.5 rounded-full px-1.5 py-0.5 text-[10px] font-medium tabular",
                  active
                    ? "bg-accent text-accent-foreground"
                    : it.countVariant
                      ? COUNT_TINT[it.countVariant]
                      : "bg-secondary text-muted-foreground",
                )}
              >
                {it.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
