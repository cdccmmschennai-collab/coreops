import { z } from "zod";

export const loginSchema = z.object({
  identifier: z
    .string()
    .min(1, "Enter your email, employee ID, or name"),
  password: z.string().min(1, "Password is required"),
});

export type LoginInput = z.infer<typeof loginSchema>;
