"use client";

/**
 * ReportPeriodCard — one Split-Day half (First Half / Second Half): status
 * selector, activity editor while working, period remarks, and a
 * benchmark-fraction hint. Location is deliberately absent — the report has
 * ONE Location (beside Date) that applies to both halves. Reuses the exact
 * same PeriodActivityEditor the Full-Day form renders, so no activity-row
 * logic is duplicated.
 *
 * A working half holds EXACTLY ONE activity. The form creates that row
 * automatically when the half starts working, so this card renders no "Add
 * Activity" control and no PM-approval flow — neither exists in Split Day
 * (both remain Full-Day only).
 *
 * Switching a half from Working to a leave/off status while it still has
 * activity rows asks for confirmation before clearing them (the rows are real
 * user input; a mis-click must not silently destroy them).
 */
import * as React from "react";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import {
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";

import {
  DAY_PART_FRACTION,
  DAY_PART_LABEL,
  DAY_STATUS_LABEL,
  PERIOD_STATUSES,
  isNoActivityDayStatus,
  type DayStatus,
} from "../schemas";
import {
  PeriodActivityEditor,
  type ActivityEditorContext,
} from "./period-activity-editor";

export type HalfKey = "first_half" | "second_half";

export function ReportPeriodCard({
  partKey,
  ctx,
  indices,
  onClearActivities,
}: {
  partKey: HalfKey;
  ctx: ActivityEditorContext;
  /** Task-row indices (into the flat `tasks` array) belonging to this half. */
  indices: number[];
  /** Clear this half's activity rows (Working -> Leave/Off confirmation). */
  onClearActivities: () => void;
}) {
  const { form } = ctx;
  const fraction = DAY_PART_FRACTION[partKey];
  const status = form.watch(`${partKey}.status`) as DayStatus | undefined;
  const working = status !== undefined && !isNoActivityDayStatus(status);
  // Working -> Leave/Off with rows present: hold the requested status until
  // the user confirms the rows may be cleared.
  const [pendingStatus, setPendingStatus] = React.useState<DayStatus | null>(null);

  const applyStatus = (next: DayStatus) => {
    form.setValue(`${partKey}.status`, next, { shouldValidate: true });
    if (isNoActivityDayStatus(next)) {
      // Location is report-level (one per day) — a half going on leave never
      // clears it; the other half may still be working.
      onClearActivities();
    }
  };

  return (
    // border-2 (not the usual 1px hairline): each half reads as its own
    // clearly-bounded section — subtle emphasis only, same border color.
    <div className="space-y-4 rounded-lg border-2 border-border p-4">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">{DAY_PART_LABEL[partKey]}</h3>
        <Badge variant={working ? "success" : "neutral"}>
          {working
            ? `Working · ${Math.round(fraction * 100)}% of daily benchmark`
            : status
              ? DAY_STATUS_LABEL[status]
              : "Select status"}
        </Badge>
      </div>

      {/* Location is NOT here: the report has one Location, beside Date. */}
      <div className="grid gap-4 sm:grid-cols-2">
        <FormField
          control={form.control}
          name={`${partKey}.status`}
          render={({ field }) => (
            <FormItem>
              <FormLabel>
                Status <span className="text-destructive">*</span>
              </FormLabel>
              <Select
                value={field.value ?? undefined}
                onValueChange={(v) => {
                  const next = v as DayStatus;
                  // Ask before clearing real activity rows on a switch from
                  // Working to a leave/off status.
                  if (
                    working &&
                    isNoActivityDayStatus(next) &&
                    indices.length > 0
                  ) {
                    setPendingStatus(next);
                    return;
                  }
                  applyStatus(next);
                }}
              >
                <FormControl>
                  <SelectTrigger>
                    <SelectValue placeholder="Select status" />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  {PERIOD_STATUSES.map((s) => (
                    <SelectItem key={s} value={s}>
                      {DAY_STATUS_LABEL[s]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FormMessage />
            </FormItem>
          )}
        />
      </div>

      {working ? (
        // Exactly ONE activity per working half: the row is created
        // automatically by the form and carries no delete control, so there is
        // no Add Activity button and no PM-approval flow here at all.
        <div className="space-y-3">
          <PeriodActivityEditor
            ctx={ctx}
            indices={indices}
            fraction={fraction}
            // The single primary row is mandatory, so it has no delete control.
            // A malformed half (>1 row, only from a hand-made payload) re-enables
            // them so the user can trim it back down to one and save.
            hideRemoveControls={indices.length <= 1}
          />
          {indices.length > 1 && (
            <p
              role="alert"
              className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive"
            >
              {DAY_PART_LABEL[partKey]} contains {indices.length} activities.
              Split Day allows only one activity per half - remove the extra
              rows before saving.
            </p>
          )}
        </div>
      ) : (
        status && (
          <p className="rounded-md border border-dashed border-border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
            {DAY_STATUS_LABEL[status]} — no activities, benchmarks or pending
            tracking for this half.
          </p>
        )
      )}

      <FormField
        control={form.control}
        name={`${partKey}.remarks`}
        render={({ field }) => (
          <FormItem>
            <FormLabel>
              {DAY_PART_LABEL[partKey]} Remarks{" "}
              <span className="font-normal text-muted-foreground">(optional)</span>
            </FormLabel>
            <FormControl>
              <Textarea
                rows={2}
                placeholder={`Anything specific to the ${DAY_PART_LABEL[partKey].toLowerCase()}?`}
                {...field}
              />
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />

      <AlertDialog
        open={pendingStatus !== null}
        onOpenChange={(open) => {
          if (!open) setPendingStatus(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              Clear {DAY_PART_LABEL[partKey]} activities?
            </AlertDialogTitle>
            <AlertDialogDescription>
              Switching this half to{" "}
              {pendingStatus ? DAY_STATUS_LABEL[pendingStatus] : ""} removes the{" "}
              {indices.length === 1 ? "activity" : `${indices.length} activities`}{" "}
              you entered for it. This cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={() => setPendingStatus(null)}>
              Keep activities
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (pendingStatus) applyStatus(pendingStatus);
                setPendingStatus(null);
              }}
            >
              Clear and switch
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
