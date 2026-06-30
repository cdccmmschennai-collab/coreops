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

import { useCreateLeave } from "../hooks";
import { LEAVE_TYPE_LABEL, LEAVE_TYPES, SELECTABLE_LEAVE_TYPES } from "../types";

const schema = z
  .object({
    leave_type: z.enum(SELECTABLE_LEAVE_TYPES),
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
      leave_type: "casual",
      start_date: "",
      end_date: "",
      reason: "",
    },
  });

  async function onSubmit(values: FormValues) {
    try {
      await create.mutateAsync({
        leave_type: values.leave_type,
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
                    {LEAVE_TYPES.map((t) => (
                      <SelectItem key={t} value={t}>
                        {LEAVE_TYPE_LABEL[t]}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FormMessage />
              </FormItem>
            )}
          />
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
