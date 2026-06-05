import * as React from "react";
import type { LucideIcon } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

/** A single labelled value in an HRMS-style detail grid. */
export function DetailField({
  label,
  value,
}: {
  label: string;
  value: React.ReactNode;
}) {
  return (
    <div className="space-y-1">
      <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </dt>
      <dd className="break-words text-sm font-medium text-foreground">
        {value || "—"}
      </dd>
    </div>
  );
}

/** A card grouping related DetailFields under an icon + title, with an optional
 *  header action (e.g. a "Change password" button). */
export function DetailSection({
  icon: Icon,
  title,
  action,
  className,
  children,
}: {
  icon?: LucideIcon;
  title: string;
  action?: React.ReactNode;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <Card className={className}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="flex items-center gap-2 text-base">
            {Icon && (
              <Icon className="h-4 w-4 text-muted-foreground" strokeWidth={1.75} />
            )}
            {title}
          </CardTitle>
          {action}
        </div>
      </CardHeader>
      <CardContent>
        <dl className="grid gap-x-6 gap-y-4 sm:grid-cols-2">{children}</dl>
      </CardContent>
    </Card>
  );
}
