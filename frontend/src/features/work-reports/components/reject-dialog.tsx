"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { toast } from "sonner";

import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Textarea } from "@/components/ui/textarea";
import { AppError } from "@/lib/api-client";

import { useRejectWorkReport } from "../hooks";
import { reviewNoteSchema, type ReviewNoteValues } from "../schemas";

export function RejectDialog({
  reportId,
  open,
  onOpenChange,
  onDone,
}: {
  reportId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onDone?: () => void;
}) {
  const form = useForm<ReviewNoteValues>({
    resolver: zodResolver(reviewNoteSchema),
    defaultValues: { review_note: "" },
  });
  const mutation = useRejectWorkReport(reportId);

  async function onSubmit(values: ReviewNoteValues) {
    try {
      await mutation.mutateAsync(values);
      toast.success("Report sent back for changes");
      form.reset();
      onDone?.();
      onOpenChange(false);
    } catch (error) {
      toast.error(error instanceof AppError ? error.message : "Could not send the report back.");
    }
  }

  function handleOpenChange(next: boolean) {
    if (!next) form.reset();
    onOpenChange(next);
  }

  return (
    <AlertDialog open={open} onOpenChange={handleOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Send report back?</AlertDialogTitle>
          <AlertDialogDescription>
            Explain what needs to change. The author can edit and resubmit.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <Form {...form}>
          <form className="space-y-4" onSubmit={form.handleSubmit(onSubmit)} noValidate>
            <FormField
              control={form.control}
              name="review_note"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Reason</FormLabel>
                  <FormControl>
                    <Textarea rows={4} placeholder="What needs to change?" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <AlertDialogFooter>
              <AlertDialogCancel type="button">Cancel</AlertDialogCancel>
              <Button type="submit" variant="danger" loading={mutation.isPending}>
                Send back
              </Button>
            </AlertDialogFooter>
          </form>
        </Form>
      </AlertDialogContent>
    </AlertDialog>
  );
}
