"use client";

import * as React from "react";

import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import {
  buildReportMonthOptions,
  REPORT_MONTH_FIELD_LABEL,
  resolveReportMonth,
} from "../production-status-report";

/**
 * The report's Month picker.
 *
 * Its own component so the dialog stays a table and this stays reusable: any
 * other view onto the same report takes the same `months` array the API sends
 * and gets the same control, with the same option list, labels and fallback.
 *
 * Presentational only. It holds no state, fetches nothing and filters nothing -
 * the value is owned by the caller and used as a query parameter, so the
 * filtering is always the backend's.
 */
export function ReportMonthSelect({
  value,
  onChange,
  months,
  disabled,
  id = "production-status-report-month",
}: {
  /** The current selection, `REPORT_MONTH_ALL` for the cumulative report. */
  value: string;
  onChange: (value: string) => void;
  /** Months that have records, from `ProductionStatusReportOut.months`. */
  months: readonly string[] | undefined;
  disabled?: boolean;
  id?: string;
}) {
  const options = React.useMemo(() => buildReportMonthOptions(months), [months]);
  // Never leave the box pointing at a month that is no longer on offer.
  const selected = resolveReportMonth(value, months);

  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id}>{REPORT_MONTH_FIELD_LABEL}</Label>
      <Select value={selected} onValueChange={onChange} disabled={disabled}>
        <SelectTrigger id={id} className="w-[13rem]">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {options.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
