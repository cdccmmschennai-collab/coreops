"use client";

import * as React from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { CountInput } from "@/components/ui/count-input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { AppError } from "@/lib/api-client";

import { useUpdateTagScope } from "../hooks";
import {
  tagScopeFormSchema,
  toTagScopeBody,
  type TagScopeFormValues,
} from "../schemas";
import {
  formatTagCount,
  isNoOpScopeChange,
  NO_CHANGE_HINT,
  parseTagCount,
  resolveTagScopeStatus,
  tagScopeErrorMessage,
  TAG_SCOPE_STATUS_LABEL,
  type TagScopeStatus,
} from "../scope";

const STATUS_OPTIONS: readonly TagScopeStatus[] = ["PROVISIONAL", "BASELINED"];

interface TagScopeDialogProps {
  projectId: string;
  /** Stored scope the form opens against — also the concurrency baseline. */
  estimatedTagCount: number | null;
  status: string | null;
  revision: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/**
 * Set / Revise Tag Scope.
 *
 * One dialog for both, because they are the same decision made at different
 * times: the only differences are the title, whether a reason is compulsory,
 * and whether there is a previous value to show. Splitting them would duplicate
 * the validation, the concurrency handling and the error mapping three ways.
 *
 * The revision number is never computed here. The form submits the revision it
 * *opened against* as `expected_revision`; the server derives the new one and
 * refuses the write outright if that baseline has moved (409).
 */
export function TagScopeDialog({
  projectId,
  estimatedTagCount,
  status,
  revision,
  open,
  onOpenChange,
}: TagScopeDialogProps) {
  const mutation = useUpdateTagScope(projectId);
  const isRevision = revision > 0;
  const currentStatus = resolveTagScopeStatus(status);

  const defaults = React.useMemo<TagScopeFormValues>(
    () => ({
      // Seeded with the stored values so a revision starts from the truth and
      // the user can change one field without retyping the other.
      estimated_tag_count: estimatedTagCount === null ? "" : String(estimatedTagCount),
      status: currentStatus ?? "PROVISIONAL",
      reason: "",
    }),
    [estimatedTagCount, currentStatus],
  );

  const form = useForm<TagScopeFormValues>({
    resolver: zodResolver(tagScopeFormSchema(isRevision)),
    defaultValues: defaults,
  });

  React.useEffect(() => {
    // Reset on open, not on close: reopening after a 409 must show the winning
    // scope that the failed save just refetched, never the stale attempt.
    if (open) form.reset(defaults);
  }, [open, defaults, form]);

  const watched = form.watch();
  const parsedCount = parseTagCount(watched.estimated_tag_count);
  // Saving the stored values verbatim is not a revision. Disabled here and
  // refused by the API independently — the UI is convenience, not the rule.
  const noChange =
    isRevision &&
    isNoOpScopeChange(
      { estimatedTagCount, status: currentStatus },
      { estimatedTagCount: parsedCount, status: watched.status },
    );

  async function onSubmit(values: TagScopeFormValues) {
    try {
      await mutation.mutateAsync(toTagScopeBody(values, revision));
      toast.success(isRevision ? "Tag scope revised" : "Tag scope set");
      onOpenChange(false);
    } catch (err) {
      const status = err instanceof AppError ? err.status : null;
      const message = err instanceof AppError ? err.message : null;
      toast.error(tagScopeErrorMessage(status, message));
      // A stale baseline can only be fixed by starting again from the stored
      // scope, which the mutation's onError has already refetched.
      if (status === 409) onOpenChange(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{isRevision ? "Revise Tag Scope" : "Set Tag Scope"}</DialogTitle>
        </DialogHeader>

        {isRevision && (
          // Nobody should have to edit a number they cannot see.
          <dl className="rounded-md border border-border bg-muted/30 px-3 py-2 text-sm">
            <div className="flex items-center justify-between gap-4">
              <dt className="text-muted-foreground">Current Estimated Tags</dt>
              <dd className="font-medium tabular">{formatTagCount(estimatedTagCount)}</dd>
            </div>
            <div className="mt-1 flex items-center justify-between gap-4">
              <dt className="text-muted-foreground">Current Status</dt>
              <dd className="font-medium">
                {currentStatus ? TAG_SCOPE_STATUS_LABEL[currentStatus] : "Not set"}
              </dd>
            </div>
            <div className="mt-1 flex items-center justify-between gap-4">
              <dt className="text-muted-foreground">Revision</dt>
              <dd className="font-medium tabular">{revision}</dd>
            </div>
          </dl>
        )}

        <Form {...form}>
          <form className="space-y-4" onSubmit={form.handleSubmit(onSubmit)} noValidate>
            <FormField
              control={form.control}
              name="estimated_tag_count"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>
                    {isRevision ? "New Estimated Tag Count" : "Estimated Tag Count"}
                  </FormLabel>
                  <FormControl>
                    {/* The repo's shared count field: digits only, no spinners
                        and no wheel-increment (which would otherwise change the
                        estimate when the user scrolls down to reach Save).
                        It permits "" and "0" mid-edit — parseTagCount is what
                        refuses those at submit. */}
                    <CountInput {...field} placeholder="e.g. 2500" />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="status"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Scope Status</FormLabel>
                  <Select value={field.value} onValueChange={field.onChange}>
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {STATUS_OPTIONS.map((s) => (
                        <SelectItem key={s} value={s}>
                          {TAG_SCOPE_STATUS_LABEL[s]}
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
                    {isRevision ? "Reason for Change" : "Reason"}
                  </FormLabel>
                  <FormControl>
                    <Textarea
                      rows={3}
                      placeholder={
                        isRevision
                          ? "e.g. Additional tags identified from new reference documents"
                          : "Initial project estimate"
                      }
                      {...field}
                    />
                  </FormControl>
                  {!isRevision && (
                    <p className="text-xs text-muted-foreground">
                      Optional. Recorded as &quot;Initial project estimate&quot; if left blank.
                    </p>
                  )}
                  <FormMessage />
                </FormItem>
              )}
            />

            {noChange && <p className="text-xs text-muted-foreground">{NO_CHANGE_HINT}</p>}

            <DialogFooter>
              <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" loading={mutation.isPending} disabled={noChange}>
                {isRevision ? "Update Scope" : "Save"}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
