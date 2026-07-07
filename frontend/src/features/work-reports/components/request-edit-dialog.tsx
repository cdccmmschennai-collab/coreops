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

import { useRequestEditWorkReport } from "../hooks";
import { editRequestSchema, type EditRequestValues } from "../schemas";

export function RequestEditDialog({
  reportId,
  open,
  onOpenChange,
}: {
  reportId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const form = useForm<EditRequestValues>({
    resolver: zodResolver(editRequestSchema),
    defaultValues: { note: "" },
  });
  const mutation = useRequestEditWorkReport(reportId);

  async function onSubmit(values: EditRequestValues) {
    try {
      await mutation.mutateAsync(values);
      toast.success("Edit request sent to the Project Head");
      form.reset();
      onOpenChange(false);
    } catch (error) {
      toast.error(error instanceof AppError ? error.message : "Could not send edit request.");
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
          <AlertDialogTitle>Request edit access?</AlertDialogTitle>
          <AlertDialogDescription>
            This report is submitted. Tell the Project Head why you need to edit it.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <Form {...form}>
          <form className="space-y-4" onSubmit={form.handleSubmit(onSubmit)} noValidate>
            <FormField
              control={form.control}
              name="note"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Reason</FormLabel>
                  <FormControl>
                    <Textarea rows={4} placeholder="Why do you need to edit this report?" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <AlertDialogFooter>
              <AlertDialogCancel type="button">Cancel</AlertDialogCancel>
              <Button type="submit" loading={mutation.isPending}>
                Send request
              </Button>
            </AlertDialogFooter>
          </form>
        </Form>
      </AlertDialogContent>
    </AlertDialog>
  );
}
