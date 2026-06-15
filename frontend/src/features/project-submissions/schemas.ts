import { z } from "zod";

export const submissionItemSchema = z.object({
  activity_type_id: z.string().uuid().nullable().optional(),
  activity_label: z.string().trim().min(1, "Activity label is required"),
  quantity: z.coerce.number().int().min(1, "Quantity must be at least 1"),
  unit: z.string().trim().min(1, "Unit is required"),
});

export const submissionFormSchema = z
  .object({
    submission_date: z.string().min(1, "Submission date is required"),
    period_start: z.string().min(1, "Period start is required"),
    period_end: z.string().min(1, "Period end is required"),
    notes: z.string().trim(),
    items: z.array(submissionItemSchema).min(1, "At least one item is required"),
  })
  .refine((v) => v.period_end >= v.period_start, {
    message: "Period end cannot be before period start",
    path: ["period_end"],
  });

export type SubmissionFormValues = z.infer<typeof submissionFormSchema>;
export type SubmissionItemFormValues = z.infer<typeof submissionItemSchema>;

export const statusUpdateSchema = z.object({
  review_note: z.string().trim(),
});

export type StatusUpdateFormValues = z.infer<typeof statusUpdateSchema>;

export const EMPTY_ITEM: SubmissionItemFormValues = {
  activity_type_id: null,
  activity_label: "",
  quantity: 1,
  unit: "",
};
