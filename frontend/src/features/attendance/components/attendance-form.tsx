"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { toast } from "sonner";

import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { AppError } from "@/lib/api-client";
import { istTodayISO } from "@/lib/ist";

import { REASON_REQUIRED_MESSAGE, isPastDate, isReasonMissing } from "../date-rules";
import { useEmployeeOptions } from "../employee-options";
import { useCreateAttendance, useUpdateAttendance } from "../hooks";
import {
  ATTENDANCE_STATUSES,
  ATTENDANCE_STATUS_LABEL,
  attendanceFormSchema,
  toCreateBody,
  toUpdateBody,
  type AttendanceFormValues,
} from "../schemas";

interface AttendanceFormProps {
  mode: "create" | "edit";
  defaultValues: AttendanceFormValues;
  recordId?: string;
}

export function AttendanceForm({ mode, defaultValues, recordId }: AttendanceFormProps) {
  const router = useRouter();
  const [formError, setFormError] = React.useState<string | null>(null);
  const { items, byId } = useEmployeeOptions();

  const form = useForm<AttendanceFormValues>({
    resolver: zodResolver(attendanceFormSchema),
    defaultValues,
  });

  const createMutation = useCreateAttendance();
  const updateMutation = useUpdateAttendance(recordId ?? "");
  const isPending = createMutation.isPending || updateMutation.isPending;

  const pastDay = isPastDate(form.watch("attendance_date"), istTodayISO());

  async function onSubmit(values: AttendanceFormValues) {
    setFormError(null);
    // Same rule the backend enforces: a past day needs a reason for the change.
    if (isReasonMissing(values.attendance_date, values.note, istTodayISO())) {
      form.setError("note", { message: REASON_REQUIRED_MESSAGE });
      return;
    }
    try {
      const result =
        mode === "create"
          ? await createMutation.mutateAsync(toCreateBody(values))
          : await updateMutation.mutateAsync(toUpdateBody(values));
      toast.success(mode === "create" ? "Attendance recorded" : "Changes saved");
      router.push(`/attendance/${result.id}`);
    } catch (error) {
      setFormError(
        error instanceof AppError ? error.message : "Something went wrong. Please try again.",
      );
    }
  }

  return (
    <Card>
      <CardContent className="pt-6">
        {formError && (
          <div
            role="alert"
            className="mb-4 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive"
          >
            {formError}
          </div>
        )}
        <Form {...form}>
          <form className="space-y-4" onSubmit={form.handleSubmit(onSubmit)} noValidate>
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField
                control={form.control}
                name="employee_id"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Employee</FormLabel>
                    {mode === "edit" ? (
                      <FormControl>
                        <Input value={byId.get(field.value) ?? field.value} disabled />
                      </FormControl>
                    ) : (
                      <Select value={field.value} onValueChange={field.onChange}>
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue placeholder="Select an employee" />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          {items.map((e) => (
                            <SelectItem key={e.id} value={e.id}>
                              {e.full_name} · {e.employee_code}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    )}
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="attendance_date"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Date</FormLabel>
                    <FormControl>
                      <Input type="date" {...field} disabled={mode === "edit"} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="status"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Status</FormLabel>
                    <Select value={field.value} onValueChange={field.onChange}>
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {ATTENDANCE_STATUSES.map((s) => (
                          <SelectItem key={s} value={s}>
                            {ATTENDANCE_STATUS_LABEL[s]}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <div className="hidden sm:block" aria-hidden />
            </div>

            <FormField
              control={form.control}
              name="note"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>
                    Reason
                    {pastDay && <span className="text-destructive"> *</span>}
                  </FormLabel>
                  <FormControl>
                    <Textarea
                      rows={2}
                      maxLength={500}
                      placeholder="Why this day was set this way"
                      aria-required={pastDay}
                      {...field}
                    />
                  </FormControl>
                  <p className="text-xs text-muted-foreground">
                    {pastDay
                      ? `${REASON_REQUIRED_MESSAGE} It is recorded in the audit trail with your name and the time.`
                      : "Recorded in the audit trail with your name and the time."}
                  </p>
                  <FormMessage />
                </FormItem>
              )}
            />

            <div className="flex justify-end gap-2 pt-2">
              <Button
                type="button"
                variant="ghost"
                onClick={() => router.back()}
                disabled={isPending}
              >
                Cancel
              </Button>
              <Button type="submit" loading={isPending}>
                {mode === "create" ? "Record attendance" : "Save changes"}
              </Button>
            </div>
          </form>
        </Form>
      </CardContent>
    </Card>
  );
}
