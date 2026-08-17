"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
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

import { useCreatePermission, useMyPermissionBalance } from "../hooks";
import {
  PERMISSION_DURATIONS,
  PERMISSION_DURATION_LABEL,
  PERMISSION_HISTORY_PATH,
  businessToday,
  formatHours,
  isDurationAffordable,
  remainingAfter,
  type PermissionDuration,
} from "../types";

// Duration is a string in the form because a <Select> value is a string; it is
// parsed back to 1 or 2 on submit. The union is what keeps a hand-typed "3" out.
const schema = z.object({
  permission_date: z.string().min(1, "Date is required"),
  duration_hours: z.enum(["1", "2"]),
  reason: z.string().trim().max(2000),
});

type FormValues = z.infer<typeof schema>;

interface Props {
  onClose: () => void;
}

/** Permission Request form. Same visual language as the Leave Request dialog -
 *  same Form primitives, same field order, same footer - with the live balance
 *  preview the leave form has no equivalent of.
 *
 *  The preview is a CONVENIENCE. The backend re-derives the balance under a lock
 *  on every approval, so nothing here is trusted as a check: an unaffordable
 *  duration is hidden to keep the form honest, not to enforce the rule. */
export function PermissionRequestDialog({ onClose }: Props) {
  const router = useRouter();
  const create = useCreatePermission();
  // The current-month balance, resolved server-side so the month boundary is
  // the Chennai business one rather than the browser's.
  const balanceQuery = useMyPermissionBalance();
  const remaining = balanceQuery.data?.remaining_hours ?? 0;
  const allowance = balanceQuery.data?.allowance_hours ?? 0;

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      // Defaults to today on the business calendar, matching how the rest of
      // CoreOps decides what "today" is.
      permission_date: businessToday(),
      duration_hours: "1",
      reason: "",
    },
  });

  const selected = Number(form.watch("duration_hours"));
  const afterApproval = remainingAfter(remaining, selected);

  // With 1h left, 2h stops being offered. If the user had already selected it
  // before the balance loaded, fall back to 1h rather than leaving the form in a
  // state the server will refuse.
  React.useEffect(() => {
    if (balanceQuery.isSuccess && !isDurationAffordable(selected, remaining) && remaining >= 1) {
      form.setValue("duration_hours", "1");
    }
  }, [balanceQuery.isSuccess, selected, remaining, form]);

  const exhausted = balanceQuery.isSuccess && remaining < 1;

  /** Leave the form for this month's history. Closes the dialog FIRST so the
   *  modal is not left mounted over the page it navigated to. */
  function openHistory() {
    onClose();
    router.push(PERMISSION_HISTORY_PATH);
  }

  async function onSubmit(values: FormValues) {
    try {
      await create.mutateAsync({
        permission_date: values.permission_date,
        duration_hours: Number(values.duration_hours) as PermissionDuration,
        reason: values.reason || null,
      });
      toast.success("Permission request submitted");
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
            name="permission_date"
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
          <FormField
            control={form.control}
            name="duration_hours"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Duration</FormLabel>
                <Select value={field.value} onValueChange={field.onChange}>
                  <FormControl>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    {PERMISSION_DURATIONS.map((hours) => (
                      <SelectItem
                        key={hours}
                        value={String(hours)}
                        disabled={
                          balanceQuery.isSuccess &&
                          !isDurationAffordable(hours, remaining)
                        }
                      >
                        {PERMISSION_DURATION_LABEL[hours]}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="reason"
            render={({ field }) => (
              <FormItem>
                <FormLabel>
                  Reason <span className="text-muted-foreground font-normal">(optional)</span>
                </FormLabel>
                <FormControl>
                  <Textarea rows={3} placeholder="Brief reason for permission" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <div className="grid grid-cols-2 gap-3 rounded-lg border border-border bg-secondary/30 px-4 py-3">
            <div>
              <div className="text-xs text-muted-foreground">Available permission</div>
              <div className="mt-0.5 text-lg font-semibold tabular">
                {balanceQuery.isLoading ? "-" : formatHours(remaining)}
              </div>
            </div>
            <div>
              <div className="text-xs text-muted-foreground">Remaining after approval</div>
              <div className="mt-0.5 text-lg font-semibold tabular">
                {balanceQuery.isLoading ? "-" : formatHours(afterApproval)}
              </div>
            </div>
          </div>

          {exhausted && (
            <p className="text-sm text-warning">
              You have used all {formatHours(allowance)} of this month&apos;s permission
              allowance. A new request can be submitted, but it can&apos;t be approved
              until next month.
            </p>
          )}

          {/* Sits between the balance preview and the footer: it answers the
              question the preview raises ("where did my hours go?") without
              competing with Submit.

              type="button" is essential - inside a <form>, a bare <button>
              defaults to type="submit" and this would file the request instead of
              navigating. It must never submit or modify the draft. */}
          <div>
            <button
              type="button"
              onClick={openHistory}
              className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
            >
              History
            </button>
          </div>

          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="ghost" onClick={onClose} disabled={create.isPending}>
              Cancel
            </Button>
            <Button type="submit" loading={create.isPending}>
              Submit
            </Button>
          </div>
        </form>
      </Form>
    </div>
  );
}
