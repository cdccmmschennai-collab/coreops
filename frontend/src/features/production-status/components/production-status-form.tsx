"use client";

import * as React from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Combobox } from "@/components/ui/combobox";
import { CountInput } from "@/components/ui/count-input";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useMaintenancePlantOptions } from "@/features/plant-master/hooks";
import { AppError } from "@/lib/api-client";

import { useCreateProductionStatus } from "../hooks";
import {
  COUNT_UNITS,
  isSaveInFlight,
  NO_ACTIVITIES_HINT,
  NO_ACTIVITIES_TITLE,
  NO_MASTER_ACTIVITIES_HINT,
  PRODUCTION_STATUS_LABEL,
  PRODUCTION_STATUS_VALUES,
  productionStatusErrorMessage,
  typedActivityValue,
  withTypedActivityOption,
  type ActivityOption,
} from "../production-status";
import {
  EMPTY_PRODUCTION_STATUS_FORM,
  productionStatusFormSchema,
  resetAfterSave,
  toProductionStatusBody,
  type ProductionStatusFormValues,
} from "../schemas";

interface ProductionStatusFormProps {
  projectId: string;
  /** Read-only "Project" — the project code, from the project the page loaded. */
  projectDisplay: string;
  /**
   * The project's Planning Plant code. Scopes the Maintenance Plant dropdown to
   * the plants that Planning Plant actually has — the same scoping the Project
   * Edit page applies. Undefined when the project has no Planning Plant, which
   * means there are no Maintenance Plants to offer at all.
   */
  planningPlantCode?: string;
  /**
   * The activities this viewer may submit for — every Activity Master activity
   * for the Head, only the ones they lead for an Activity Lead.
   */
  activities: ActivityOption[];
  /**
   * May this viewer type an activity that is not in Activity Master? The Head
   * only. It is why the Head can never be stuck with an empty dropdown, and why
   * the two empty states below say different things.
   */
  canTypeActivity: boolean;
}

/**
 * Save Status — the single entry form.
 *
 * Every save is a POST that APPENDS one record. There is no edit mode and no
 * "load the current values into the form" step, because production status is
 * append-only: correcting a figure means recording the corrected update, which
 * supersedes the previous one for display while leaving it in the history.
 *
 * Nothing on this screen is calculated. The four counts, the status, the
 * revision, the completion date and the remarks are submitted exactly as
 * entered; what the "current" status then is, is the backend's answer.
 */
export function ProductionStatusForm({
  projectId,
  projectDisplay,
  planningPlantCode,
  activities,
  canTypeActivity,
}: ProductionStatusFormProps) {
  const mutation = useCreateProductionStatus(projectId);

  // The SAME source the Project Edit page's Maintenance Plant dropdown reads:
  // `useMaintenancePlantOptions(activeOnly, planningPlantCode, enabled)` over
  // GET /plants/maintenance-plants. No second plant lookup exists, so this
  // dropdown can never offer a plant the POST would reject — the backend
  // validates against that same scoped list.
  const { options: plantOptions, isLoading: plantsLoading } =
    useMaintenancePlantOptions(true, planningPlantCode, !!planningPlantCode);

  const form = useForm<ProductionStatusFormValues>({
    resolver: zodResolver(productionStatusFormSchema),
    defaultValues: EMPTY_PRODUCTION_STATUS_FORM,
  });

  // True from the instant Save is pressed (react-hook-form sets isSubmitting
  // before it runs the async zod validation) until the POST has answered. The
  // Button disables itself on `loading`, so the second click of a double-click
  // has nothing to hit and only one record is appended.
  //
  // Not a de-duplication rule: two INTENTIONAL saves with identical values are
  // legitimate history and both still reach the append-only table.
  const saving = isSaveInFlight({
    isPending: mutation.isPending,
    isSubmitting: form.formState.isSubmitting,
  });

  async function onSubmit(values: ProductionStatusFormValues) {
    // Belt and braces for the case a submit is triggered without the button
    // (Enter in a text field while a save is already in flight).
    if (mutation.isPending) return;
    try {
      await mutation.mutateAsync(toProductionStatusBody(values));
      toast.success("Production status saved");
      // Keeps revision/activity/status, clears what was asserted about THIS
      // update so the next save can never inherit the last one's numbers.
      form.reset(resetAfterSave(values));
    } catch (err) {
      const status = err instanceof AppError ? err.status : null;
      const message = err instanceof AppError ? err.message : null;
      toast.error(productionStatusErrorMessage(status, message));
    }
  }

  // Only a Lead can genuinely run out of activities: their options are the ones
  // they lead. A Head always has the form, because they see all of Activity
  // Master AND may type an activity that is not in it - an empty master list is
  // a hint inside the form, never a dead end.
  if (activities.length === 0 && !canTypeActivity) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Update Production Status</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm font-medium text-foreground">{NO_ACTIVITIES_TITLE}</p>
          <p className="mt-0.5 text-sm text-muted-foreground">{NO_ACTIVITIES_HINT}</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Update Production Status</CardTitle>
      </CardHeader>
      <CardContent>
        <Form {...form}>
          <form className="space-y-4" onSubmit={form.handleSubmit(onSubmit)} noValidate>
            {/* Project and Maintenance Plant on one row, half the width each -
                they are the two things that say WHERE this update belongs, and
                they read as a pair. Project is read-only and derived; it is
                never an input and never stored again on the record (it hangs
                off project_id). */}
            {/* items-start keeps both fields on the same top line even when
                one of them shows a validation message underneath. The Project
                block below is structurally identical to a FormItem - the same
                `space-y-2`, the same `Label`, and the same h-9 control height
                as the Combobox next to it - so the two labels and the two boxes
                line up exactly. */}
            <div className="grid items-start gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label>Project</Label>
                <div className="flex h-9 w-full items-center rounded-md border border-input bg-muted/30 px-3">
                  <span className="truncate font-mono text-sm font-medium">
                    {projectDisplay}
                  </span>
                </div>
              </div>

              {/* Maintenance Plant — selectable, and stored ON the record.
                  Deliberately NOT the project's Planning Plant: the Planning
                  Plant only decides WHICH plants may be offered here.

                  Optional throughout. A project whose Planning Plant has no
                  Maintenance Plants (or has no Planning Plant at all) simply
                  offers none, and the form still saves — the plant is left
                  unset rather than invented, and the report leaves that part of
                  the Project / Plant value out. */}
              <FormField
                control={form.control}
                name="maintenance_plant_id"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Maintenance Plant</FormLabel>
                    <FormControl>
                      <Combobox
                        value={field.value || ""}
                        onValueChange={field.onChange}
                        options={plantOptions}
                        placeholder={
                          !planningPlantCode
                            ? "No maintenance plants for this project"
                            : plantsLoading
                              ? "Loading plants…"
                              : "Select maintenance plant…"
                        }
                        searchPlaceholder="Search maintenance plants…"
                        emptyMessage="No plants for this project's Planning Plant."
                        disabled={!planningPlantCode}
                        allowClear
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <FormField
                control={form.control}
                name="revision"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Revision</FormLabel>
                    <FormControl>
                      {/* Entered per update and owned by the record. Changing it
                          starts a separate current status and a separate
                          history — it never rewrites the previous revision. */}
                      <Input placeholder="e.g. REV-0" autoComplete="off" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              {/* Searchable, and creatable for the Head. The Head's list is
                  every Activity Master activity; a Lead's is the ones they
                  lead. Typing a name the list does not have offers "Create
                  ...", which records the update against that name WITHOUT
                  adding it to Activity Master - see typedActivityValue and the
                  backend's activity_label column. */}
              <FormField
                control={form.control}
                name="activity_id"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Activity</FormLabel>
                    <FormControl>
                      <Combobox
                        value={field.value || ""}
                        onValueChange={field.onChange}
                        // The typed name is appended only while it is the
                        // selection, so the field shows what was typed instead
                        // of looking empty.
                        options={withTypedActivityOption(
                          activities,
                          field.value,
                        ).map((a) => ({ value: a.id, label: a.label }))}
                        placeholder={
                          canTypeActivity
                            ? "Select or type an activity…"
                            : "Select an activity"
                        }
                        searchPlaceholder={
                          canTypeActivity
                            ? "Search, or type a new activity…"
                            : "Search activities…"
                        }
                        emptyMessage={
                          canTypeActivity
                            ? NO_MASTER_ACTIVITIES_HINT
                            : "No activities available."
                        }
                        allowCreate={canTypeActivity}
                        onCreateNew={(typed) =>
                          field.onChange(typedActivityValue(typed))
                        }
                        allowClear
                      />
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
                    <FormLabel>Status</FormLabel>
                    <Select value={field.value} onValueChange={field.onChange}>
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {PRODUCTION_STATUS_VALUES.map((s) => (
                          <SelectItem key={s} value={s}>
                            {PRODUCTION_STATUS_LABEL[s]}
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
                name="completed_on"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Completed On</FormLabel>
                    <FormControl>
                      {/* Never pre-filled with today: a completion date is a
                          claim the user makes, not a default. Optional for both
                          statuses, exactly as the API accepts it. */}
                      <Input type="date" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            {/* Four independent units, four inputs, four equal boxes. They are
                never added together or collapsed into one count. */}
            <div>
              <p className="mb-2 text-sm font-medium text-foreground">Count</p>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                {COUNT_UNITS.map((unit) => (
                  <FormField
                    key={unit.key}
                    control={form.control}
                    name={unit.key}
                    render={({ field }) => (
                      <FormItem className="rounded-md border border-border p-2">
                        <FormLabel className="text-xs tracking-wide text-muted-foreground">
                          {unit.label}
                        </FormLabel>
                        <FormControl>
                          {/* Digits only, no spinners, no wheel-increment —
                              the repo's shared count field. Blank is allowed
                              and is sent as 0, matching the API's contract for
                              an unused unit. */}
                          <CountInput className="text-right tabular" placeholder="-" {...field} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                ))}
              </div>
            </div>

            <FormField
              control={form.control}
              name="remarks"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Remarks</FormLabel>
                  <FormControl>
                    <Textarea
                      rows={3}
                      placeholder="Optional note about this update"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <div className="flex justify-end">
              <Button type="submit" loading={saving}>
                Save Status
              </Button>
            </div>
          </form>
        </Form>
      </CardContent>
    </Card>
  );
}
