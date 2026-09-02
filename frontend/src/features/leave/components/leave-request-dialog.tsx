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
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { AppError } from "@/lib/api-client";

import { useCreateLeave, useLeaveClassificationPreview } from "../hooks";
import { LEAVE_CLASSIFICATION_LABEL } from "../types";

// Leave type stays on the form, but it is READ-ONLY. Normal/Special is decided
// by how many working days the chosen dates cost, so it is shown - updating as
// the dates change - rather than picked. The value comes from the backend's own
// working-day count, never from arithmetic done here, which is why the field
// can never promise a classification the saved request disagrees with.
const schema = z
  .object({
    start_date: z.string().min(1, "Start date is required"),
    end_date: z.string().min(1, "End date is required"),
    reason: z.string().trim().max(2000),
  })
  .refine((v) => v.end_date >= v.start_date, {
    message: "End date must be on or after start date",
    path: ["end_date"],
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
      start_date: "",
      end_date: "",
      reason: "",
    },
  });

  const startDate = form.watch("start_date");
  const endDate = form.watch("end_date");
  const preview = useLeaveClassificationPreview(startDate, endDate);

  // Blank until there is a range to classify - a placeholder value would be a
  // guess, and this field exists precisely so the employee does not have to
  // guess. The hook keeps the previous answer on screen while a new one is in
  // flight, so the field does not blank out on every keystroke.
  const leaveTypeText = preview.data
    ? LEAVE_CLASSIFICATION_LABEL[preview.data.classification]
    : "";

  async function onSubmit(values: FormValues) {
    try {
      await create.mutateAsync({
        start_date: values.start_date,
        end_date: values.end_date,
        reason: values.reason || null,
      });
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
          {/* Deliberately NOT FormField/FormItem/FormLabel: those read the
              react-hook-form field context, and this is not a form field - it
              is a derived read-out with no value to submit or validate. Plain
              Label + Input, styled to match the fields around it. */}
          <div className="space-y-2">
            <Label htmlFor="leave-classification">Leave type</Label>
            <Input
              id="leave-classification"
              readOnly
              disabled
              value={leaveTypeText}
              placeholder="Set by the dates you choose"
            />
          </div>
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
