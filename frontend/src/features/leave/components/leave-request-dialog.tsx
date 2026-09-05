"use client";

import * as React from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
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

import { useCreateLeave, useLeaveClassificationPreview } from "../hooks";
import {
  LEAVE_TYPE_CHOICES,
  LEAVE_TYPE_CHOICE_LABEL,
  isHalfDayChoice,
  leaveClassificationNote,
  leaveCreateBody,
} from "../types";

// LEAVE TYPE IS A SELECTION NOW, BUT NOT AN OVERRIDE.
//
// It used to be a frozen read-out of the backend's Normal/Special answer. It is
// a real dropdown since half-day leave (Phase 2), because "which half of the
// day" is genuinely the employee's to state and nothing can derive it. What the
// dropdown picks is the SHAPE OF THE REQUEST:
//
//   Normal / Special                  From + To, multi-day allowed - unchanged
//                                     in every respect, including that the
//                                     backend still decides which of the two it
//                                     really is from the working days the dates
//                                     cost. The note under the field reports
//                                     that live answer, so choosing "Normal" for
//                                     a fortnight is corrected on screen rather
//                                     than silently contradicted on save.
//   Half Day (First) / (Second)       ONE Date field, sent as start === end with
//                                     `half_day_period`.
//
// The date rules are split by choice for exactly that reason: a half day is half
// of ONE day, so the multi-day pair is not merely discouraged for it, it is not
// offered. `leaveCreateBody` is the only place the choice becomes a payload.
const schema = z
  .object({
    leave_type: z.enum(LEAVE_TYPE_CHOICES),
    start_date: z.string(),
    end_date: z.string(),
    half_day_date: z.string(),
    reason: z.string().trim().max(2000),
  })
  .superRefine((v, ctx) => {
    if (isHalfDayChoice(v.leave_type)) {
      if (!v.half_day_date) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: "Date is required",
          path: ["half_day_date"],
        });
      }
      return;
    }
    if (!v.start_date) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: "Start date is required",
        path: ["start_date"],
      });
    }
    if (!v.end_date) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: "End date is required",
        path: ["end_date"],
      });
    }
    if (v.start_date && v.end_date && v.end_date < v.start_date) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: "End date must be on or after start date",
        path: ["end_date"],
      });
    }
  });

type FormValues = z.infer<typeof schema>;

interface Props {
  onClose: () => void;
}

export function LeaveRequestDialog({ onClose }: Props) {
  const create = useCreateLeave();
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      // Normal is the default because it is what the form has always filed -
      // opening the dialog and filling in two dates behaves exactly as before.
      leave_type: "normal",
      start_date: "",
      end_date: "",
      half_day_date: "",
      reason: "",
    },
  });

  const leaveType = form.watch("leave_type");
  const halfDay = isHalfDayChoice(leaveType);
  const startDate = form.watch("start_date");
  const endDate = form.watch("end_date");

  // Asked only for the full-day shape: a half day is one day and already says
  // what it is. The hook is disabled until both dates are present and in order,
  // and keeps the previous answer on screen while a new one is in flight.
  const preview = useLeaveClassificationPreview(
    halfDay ? "" : startDate,
    halfDay ? "" : endDate,
  );
  const classificationNote = leaveClassificationNote(leaveType, preview.data);

  async function onSubmit(values: FormValues) {
    try {
      await create.mutateAsync(leaveCreateBody(values));
      toast.success("Leave request submitted");
      onClose();
    } catch (err) {
      toast.error(err instanceof AppError ? err.message : "Could not submit request.");
    }
  }

  return (
    <div className="space-y-4">
      <Form {...form}>
        <form className="space-y-4" onSubmit={form.handleSubmit(onSubmit)} noValidate>
          <FormField
            control={form.control}
            name="leave_type"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Leave type</FormLabel>
                <Select value={field.value} onValueChange={field.onChange}>
                  <FormControl>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    {LEAVE_TYPE_CHOICES.map((choice) => (
                      <SelectItem key={choice} value={choice}>
                        {LEAVE_TYPE_CHOICE_LABEL[choice]}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {classificationNote && (
                  <p className="text-xs text-muted-foreground">{classificationNote}</p>
                )}
                <FormMessage />
              </FormItem>
            )}
          />

          {/* ONE field or TWO, never both. A half day cannot span a range, so
              the range is not offered for it - the rule is expressed by what is
              on screen rather than by an error after the fact. Switching back
              restores whatever was already typed into the other shape, because
              both live in the form state side by side. */}
          {halfDay ? (
            <FormField
              control={form.control}
              name="half_day_date"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Date</FormLabel>
                  <FormControl>
                    <Input type="date" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
          ) : (
            <div className="grid grid-cols-2 gap-4">
              <FormField
                control={form.control}
                name="start_date"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>From</FormLabel>
                    <FormControl>
                      <Input type="date" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="end_date"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>To</FormLabel>
                    <FormControl>
                      <Input type="date" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
          )}
          <FormField
            control={form.control}
            name="reason"
            render={({ field }) => (
              <FormItem>
                <FormLabel>
                  Reason <span className="text-muted-foreground font-normal">(optional)</span>
                </FormLabel>
                <FormControl>
                  <Textarea rows={3} placeholder="Brief reason for leave" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="ghost" onClick={onClose} disabled={create.isPending}>
              Cancel
            </Button>
            <Button type="submit" loading={create.isPending}>
              Submit request
            </Button>
          </div>
        </form>
      </Form>
    </div>
  );
}
