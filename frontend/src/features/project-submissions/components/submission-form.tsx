"use client";

import * as React from "react";
import { useFieldArray, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

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
import { Textarea } from "@/components/ui/textarea";
import { AppError } from "@/lib/api-client";

import { useCreateSubmission, useUpdateSubmission } from "../hooks";
import {
  EMPTY_ITEM,
  submissionFormSchema,
  type SubmissionFormValues,
} from "../schemas";
import type { Submission } from "../types";

interface SubmissionFormProps {
  projectId: string;
  existing?: Submission;
  onDone: () => void;
  onCancel: () => void;
}

export function SubmissionForm({
  projectId,
  existing,
  onDone,
  onCancel,
}: SubmissionFormProps) {
  const isEdit = !!existing;

  const form = useForm<SubmissionFormValues>({
    resolver: zodResolver(submissionFormSchema),
    defaultValues: existing
      ? {
          submission_date: existing.submission_date,
          period_start: existing.period_start,
          period_end: existing.period_end,
          notes: existing.notes ?? "",
          items: existing.items.map((i) => ({
            activity_type_id: i.activity_type_id ?? null,
            activity_label: i.activity_label,
            quantity: i.quantity,
            unit: i.unit,
          })),
        }
      : {
          submission_date: "",
          period_start: "",
          period_end: "",
          notes: "",
          items: [{ ...EMPTY_ITEM }],
        },
  });

  const { fields, append, remove } = useFieldArray({
    control: form.control,
    name: "items",
  });

  const createMut = useCreateSubmission(projectId);
  const updateMut = useUpdateSubmission(projectId, existing?.id ?? "");
  const isPending = createMut.isPending || updateMut.isPending;

  async function onSubmit(values: SubmissionFormValues) {
    try {
      if (isEdit) {
        await updateMut.mutateAsync({
          submission_date: values.submission_date,
          period_start: values.period_start,
          period_end: values.period_end,
          notes: values.notes || null,
          items: values.items,
        });
        toast.success("Submission updated");
      } else {
        await createMut.mutateAsync({
          submission_date: values.submission_date,
          period_start: values.period_start,
          period_end: values.period_end,
          notes: values.notes || null,
          items: values.items,
        });
        toast.success("Submission created");
      }
      onDone();
    } catch (err) {
      toast.error(err instanceof AppError ? err.message : "Something went wrong");
    }
  }

  return (
    <Form {...form}>
      <form className="space-y-4" onSubmit={form.handleSubmit(onSubmit)} noValidate>
        <div className="grid gap-4 sm:grid-cols-3">
          <FormField
            control={form.control}
            name="submission_date"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Submission date</FormLabel>
                <FormControl><Input type="date" {...field} /></FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="period_start"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Period start</FormLabel>
                <FormControl><Input type="date" {...field} /></FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="period_end"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Period end</FormLabel>
                <FormControl><Input type="date" {...field} /></FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>

        <FormField
          control={form.control}
          name="notes"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Notes <span className="font-normal text-muted-foreground">(optional)</span></FormLabel>
              <FormControl><Textarea rows={2} {...field} /></FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        {/* Items */}
        <div>
          <div className="mb-2 text-sm font-medium">Submission items</div>
          <div className="space-y-2">
            {fields.map((field, idx) => (
              <div key={field.id} className="grid grid-cols-[1fr_auto_auto_auto] items-start gap-2">
                <FormField
                  control={form.control}
                  name={`items.${idx}.activity_label`}
                  render={({ field: f }) => (
                    <FormItem>
                      {idx === 0 && <FormLabel className="text-xs">Activity</FormLabel>}
                      <FormControl>
                        <Input placeholder="e.g. FMTL Data Population" {...f} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name={`items.${idx}.quantity`}
                  render={({ field: f }) => (
                    <FormItem className="w-24">
                      {idx === 0 && <FormLabel className="text-xs">Qty</FormLabel>}
                      <FormControl>
                        <Input type="number" min={1} placeholder="0" {...f} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name={`items.${idx}.unit`}
                  render={({ field: f }) => (
                    <FormItem className="w-28">
                      {idx === 0 && <FormLabel className="text-xs">Unit</FormLabel>}
                      <FormControl>
                        <Input placeholder="Tags" {...f} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <div className={idx === 0 ? "mt-6" : ""}>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => remove(idx)}
                    disabled={fields.length === 1}
                    aria-label="Remove item"
                  >
                    <Trash2 className="h-4 w-4 text-muted-foreground" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
          {form.formState.errors.items?.root && (
            <p className="mt-1 text-xs text-destructive">
              {form.formState.errors.items.root.message}
            </p>
          )}
          {/* items min-1 message lives on the array itself */}
          {typeof form.formState.errors.items?.message === "string" && (
            <p className="mt-1 text-xs text-destructive">
              {form.formState.errors.items.message}
            </p>
          )}
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="mt-2"
            onClick={() => append({ ...EMPTY_ITEM })}
          >
            <Plus className="h-4 w-4" />
            Add item
          </Button>
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="ghost" onClick={onCancel} disabled={isPending}>
            Cancel
          </Button>
          <Button type="submit" loading={isPending}>
            {isEdit ? "Save changes" : "Create submission"}
          </Button>
        </div>
      </form>
    </Form>
  );
}
