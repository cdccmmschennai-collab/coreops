import { ArrowDown, ArrowUp } from "lucide-react";

import { cn } from "@/lib/utils";

export interface KpiProps {
  label: string;
  value: string;
  delta?: { dir: "up" | "down"; text: string };
}

/** KPI tile — label, big tabular value, optional delta. Matches app.css `.kpi`. */
export function Kpi({ label, value, delta }: KpiProps) {
  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-1 whitespace-nowrap text-[28px] font-semibold leading-none tracking-tight tabular">
        {value}
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
    </div>
  );
}

export function KpiGrid({ children }: { children: React.ReactNode }) {
  return <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">{children}</div>;
}
