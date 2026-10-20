"use client";

import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { AppError } from "@/lib/api-client";

import { useCreateCompOff } from "../hooks";
import {
  addDaysIso,
  businessToday,
  compOffErrorMessage,
  hasErrors,
  validateCompOffDates,
  type CompOffDateErrors,
} from "../types";

/** The employee's Comp Off request. Two dates, one request: the day they
 *  worked and the day they want off in return. Whose request it is comes from
 *  the session on the server - nothing here names an employee.
 *
 *  The checks below only catch what the browser can know (future worked day,
 *  past day off, same date). Whether the worked day was a non-working day, has a
 *  submitted report with activities, and whether either date is already taken
 *  is decided by the server, and its message is shown as-is. */
export function CompOffRequestForm() {
  const create = useCreateCompOff();
  const today = React.useMemo(() => businessToday(), []);
  const [workedDate, setWorkedDate] = React.useState("");
  const [offDate, setOffDate] = React.useState("");
  const [reason, setReason] = React.useState("");
  const [errors, setErrors] = React.useState<CompOffDateErrors>({});

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    // A second click while the first submission is in flight does nothing.
    if (create.isPending) return;
    const found = validateCompOffDates(workedDate, offDate, today);
    setErrors(found);
    if (hasErrors(found)) return;
    try {
      await create.mutateAsync({
        worked_date: workedDate,
        off_date: offDate,
        reason: reason.trim() || null,
      });
      toast.success("Comp off request submitted");
      setWorkedDate("");
      setOffDate("");
      setReason("");
    } catch (err) {
      // The inputs are kept so the employee can correct a date and resubmit.
      toast.error(
        err instanceof AppError
          ? compOffErrorMessage(err.status, err.message, "submit the request")
          : compOffErrorMessage(undefined, undefined, "submit the request"),
      );
    }
  }

  return (
    <Card>
      <CardHeader className="border-b border-border px-5 py-3.5">
        <CardTitle className="text-base">Request Comp Off</CardTitle>
      </CardHeader>
      <CardContent className="pt-5">
        <p className="mb-4 text-sm text-muted-foreground">
          Worked on a holiday or non-working day? Ask for a working day off in return.
        </p>
        <form className="space-y-4" onSubmit={onSubmit} noValidate>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="comp-off-worked-date">Day you worked</Label>
              <Input
                id="comp-off-worked-date"
                type="date"
                max={today}
                value={workedDate}
                onChange={(e) => setWorkedDate(e.target.value)}
                aria-invalid={Boolean(errors.worked_date)}
                aria-describedby="comp-off-worked-date-help"
              />
              <p id="comp-off-worked-date-help" className="text-xs text-muted-foreground">
                The holiday or non-working day you came in to work.
              </p>
              {errors.worked_date && (
                <p className="text-sm text-destructive" role="alert">
                  {errors.worked_date}
                </p>
              )}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="comp-off-off-date">Day off you want</Label>
              <Input
                id="comp-off-off-date"
                type="date"
                min={addDaysIso(today, 1)}
                value={offDate}
                onChange={(e) => setOffDate(e.target.value)}
                aria-invalid={Boolean(errors.off_date)}
                aria-describedby="comp-off-off-date-help"
              />
              <p id="comp-off-off-date-help" className="text-xs text-muted-foreground">
                A future working day. Request it before that day.
              </p>
              {errors.off_date && (
                <p className="text-sm text-destructive" role="alert">
                  {errors.off_date}
                </p>
              )}
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="comp-off-reason">
              Reason <span className="font-normal text-muted-foreground">(optional)</span>
            </Label>
            <Textarea
              id="comp-off-reason"
              rows={2}
              maxLength={2000}
              placeholder="What you worked on that day"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </div>
          <div className="flex justify-end">
            <Button type="submit" loading={create.isPending} disabled={create.isPending}>
              Submit request
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
