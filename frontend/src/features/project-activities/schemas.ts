import { z } from "zod";

export const activityFormSchema = z.object({
  activity_type_id: z.string().uuid().nullable().optional(),
  title: z.string().trim().min(1, "Title is required").max(500),
  status: z.enum(["open", "in_progress", "closed"]).default("open"),
  assigned_to_id: z.string().uuid().nullable().optional(),
  target_date: z.string().optional(),
  remarks: z.string().trim().optional(),
  sort_order: z.coerce.number().int().default(0),
});

export type ActivityFormValues = z.infer<typeof activityFormSchema>;

export const statusOnlySchema = z.object({
  status: z.enum(["open", "in_progress", "closed"]),
  remarks: z.string().trim().optional(),
});

export type StatusOnlyValues = z.infer<typeof statusOnlySchema>;
