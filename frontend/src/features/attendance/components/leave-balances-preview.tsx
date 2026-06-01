import { Card, CardContent } from "@/components/ui/card";

import { PreviewBanner } from "./preview-banner";

const BALANCES = [
  { type: "Casual leave", code: "CL", used: 4, total: 12, bar: "bg-sky-500" },
  { type: "Sick leave", code: "SL", used: 2, total: 12, bar: "bg-violet-500" },
  { type: "Earned leave", code: "EL", used: 5, total: 24, bar: "bg-emerald-500" },
  { type: "Comp off", code: "CO", used: 1, total: 3, bar: "bg-amber-500" },
  { type: "Bereavement", code: "BL", used: 0, total: 3, bar: "bg-rose-500" },
  { type: "Parental", code: "PL", used: 0, total: 90, bar: "bg-teal-500" },
];

export function LeaveBalancesPreview() {
  return (
    <div>
      <PreviewBanner>
        leave balances arrive with the Leave module. Figures shown are sample data.
      </PreviewBanner>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {BALANCES.map((b) => {
          const remain = b.total - b.used;
          const pct = (b.used / b.total) * 100;
          return (
            <Card key={b.code}>
              <CardContent className="p-5">
                <div className="mb-3 flex items-start justify-between">
                  <div>
                    <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                      {b.code}
                    </div>
                    <div className="mt-0.5 text-sm font-semibold">{b.type}</div>
                  </div>
                </div>
                <div className="flex items-baseline gap-2">
                  <span className="tabular text-[28px] font-semibold">{remain}</span>
                  <span className="text-xs text-muted-foreground">days remaining</span>
                </div>
                <div className="mt-2.5 h-1.5 overflow-hidden rounded-full bg-secondary">
                  <div className={`h-full ${b.bar} opacity-90`} style={{ width: `${pct}%` }} />
                </div>
                <div className="mt-1.5 flex justify-between text-[11px] tabular text-muted-foreground">
                  <span>{b.used} used</span>
                  <span>{b.total} total</span>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
