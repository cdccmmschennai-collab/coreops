"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { zodResolver } from "@hookform/resolvers/zod";
import { useFieldArray, useForm } from "react-hook-form";
import { ArrowRight, Plus, Send, Trash2 } from "lucide-react";
import { toast } from "sonner";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
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
import { Separator } from "@/components/ui/separator";
import { Tabs } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { useActivities, useSubActivityOptions } from "@/features/activity-master/hooks";
import {
  isQuantityBenchmark,
  type RelevantCountField,
} from "@/features/activity-master/types";
import {
  useCreateActivityRequest,
  useDeleteActivityRequest,
  useMyActivityRequests,
} from "@/features/activity-requests/hooks";
import type { ActivityRequest } from "@/features/activity-requests/types";
import { useAuth } from "@/features/auth/auth-provider";
import { useEmployeeOptions } from "@/features/attendance/employee-options";
import { AppError } from "@/lib/api-client";
import { features } from "@/lib/env";
import { formatInt } from "@/lib/format";

import type { OpenTask } from "../types";
import {
  useCreateWorkReport,
  useOpenTasks,
  useUpdateWorkReport,
  useWorkReportList,
} from "../hooks";
import { useProjectOptions } from "../project-options";
import {
  DAY_PART_FRACTION,
  DAY_PART_LABEL,
  DAY_STATUS_LABEL,
  DAY_STATUSES,
  EMPTY_HALF_PERIOD,
  EMPTY_TASK_ROW,
  WORK_LOCATION_LABEL,
  WORK_LOCATIONS,
  hoursToMinutes,
  isNoActivityDayStatus,
  toCreateBody,
  toUpdateBody,
  workReportFormSchema,
  type DayPart,
  type WorkReportFormValues,
} from "../schemas";
import {
  LIFECYCLE_LABEL,
  LIFECYCLE_VARIANT,
  PeriodActivityEditor,
  countFieldName,
  type ActivityEditorContext,
} from "./period-activity-editor";
import { ReportPeriodCard, type HalfKey } from "./report-period-card";
import { clearHalf, reconcileHalves } from "../split-period-rows";

interface WorkReportFormProps {
  mode: "create" | "edit";
  defaultValues: WorkReportFormValues;
  reportId?: string;
}

// Second activities under these parent Activities are routine (meetings /
// training) rather than extra project work, so they don't need PM approval —
// they save straight onto the report like the first activity. Every other
// parent Activity still routes a second activity through the PM request flow.
// Matched on the parent Activity name (upper-cased, trimmed).
const NO_APPROVAL_ACTIVITIES = new Set([
  "PROJECT MEETING",
  "TRAINING",
  "TRAINER",
]);

export function WorkReportForm({ mode, defaultValues, reportId }: WorkReportFormProps) {
  const router = useRouter();
  const [formError, setFormError] = React.useState<string | null>(null);

  const { employeeId } = useAuth();
  const { byId: empById } = useEmployeeOptions();
  const { items: projects, byId: projById } = useProjectOptions();
  const { data: activities } = useActivities(true);
  const { items: subActivities, byId: subActivityById } = useSubActivityOptions();

  const employeeName = employeeId ? (empById.get(employeeId) ?? "—") : "—";

  // Project combobox options — RBAC list + ghost entries for projects in
  // existing tasks that are no longer accessible (archived / membership lost).
  // Ghost entries are display-only; the backend still validates on submit.
  const projectOptions = React.useMemo(() => {
    const base = projects.map((p) => ({
      value: p.id,
      label: p.name,
      sublabel: p.code,
      description: p.client ?? undefined,
      keywords: [p.code, p.name, p.client ?? "", p.job_code_code ?? ""],
    }));
    if (mode !== "edit") return base;
    const inList = new Set(projects.map((p) => p.id));
    const ghosts: (typeof base)[0][] = [];
    const seen = new Set<string>();
    for (const t of defaultValues.tasks) {
      if (t.project_id && !inList.has(t.project_id) && t.project_name && !seen.has(t.project_id)) {
        seen.add(t.project_id);
        ghosts.push({
          value: t.project_id,
          label: t.project_name,            // string (narrowed by if guard)
          sublabel: t.project_code ?? "",   // string (coerce undefined → "")
          description: undefined,
          keywords: [t.project_code ?? "", t.project_name],
        });
      }
    }
    return [...base, ...ghosts];
  }, [projects, mode, defaultValues.tasks]);

  // Activity Master combobox options (Activity → Sub-Activity cascade).
  const activityOptions = React.useMemo(
    () => (activities ?? []).map((a) => ({ value: a.id, label: a.name })),
    [activities],
  );
  const activityById = React.useMemo(
    () => new Map((activities ?? []).map((a) => [a.id, a])),
    [activities],
  );
  const subActivityOptionsByActivity = React.useMemo(() => {
    const map = new Map<string, { value: string; label: string }[]>();
    for (const s of subActivities) {
      const list = map.get(s.activity_id) ?? [];
      list.push({ value: s.id, label: s.name });
      map.set(s.activity_id, list);
    }
    return map;
  }, [subActivities]);

  const form = useForm<WorkReportFormValues>({
    resolver: zodResolver(workReportFormSchema),
    defaultValues,
  });
  const { fields, append, remove, replace } = useFieldArray({
    control: form.control,
    name: "tasks",
  });

  // ── Day format (Full Day / Split Day, feature-flagged) ─────────────────────
  const dayFormat = form.watch("day_format");
  const splitEnabled = features.reportDayParts;
  const isSplit = splitEnabled && dayFormat === "split_day";

  const watchedTasks = form.watch("tasks");
  const reportDate = form.watch("report_date");

  /** Task-row indices belonging to one day part. */
  const indicesOf = React.useCallback(
    (part: DayPart) =>
      (watchedTasks ?? [])
        .map((t, i) => (t.day_part === part ? i : -1))
        .filter((i) => i >= 0),
    [watchedTasks],
  );

  // Full Day and Split Day are INDEPENDENT formats — never two synchronized
  // views over one task array. A switch converts nothing: the current
  // format's mode-specific state (status(es), activity rows, remarks,
  // continuation/draft bookkeeping) is cleared and the destination starts
  // blank. Only the report-level Date, Office Location and Query / Issues
  // survive. requestDayFormat below asks for confirmation first whenever the
  // current format holds meaningful entered data.
  function switchDayFormat(next: "full_day" | "split_day") {
    if (next === dayFormat) return;
    form.setValue("day_status", undefined);
    form.setValue("remarks", "");
    form.setValue("first_half", { ...EMPTY_HALF_PERIOD });
    form.setValue("second_half", { ...EMPTY_HALF_PERIOD });
    // Replace the rows wholesale: no hidden rows, no continuation/WorkItem
    // state and no PM-approval draft can ride into the other format. Split
    // starts with no rows (each half adds its own); Full Day with one blank.
    replace(next === "split_day" ? [] : [{ ...EMPTY_TASK_ROW }]);
    setDraftPart(null);
    setStartNewRows(new Set());
    form.setValue("day_format", next, { shouldValidate: false });
  }

  // A format switch that would discard entered data is held here until the
  // user confirms it in the dialog below.
  const [pendingFormat, setPendingFormat] =
    React.useState<"full_day" | "split_day" | null>(null);

  /** Whether one task row holds anything the user actually entered. */
  function rowHasData(t: WorkReportFormValues["tasks"][number]): boolean {
    return !!(
      t.project_id || t.activity_id || t.sub_activity_id ||
      t.description.trim() || t.activity_type.trim() ||
      t.work_item_id || t.is_completed ||
      t.task_hours.trim() || t.duration_hours.trim() ||
      Number(t.tags_count) > 0 || Number(t.docs_count) > 0 ||
      Number(t.bom_count) > 0 || Number(t.spares_count) > 0 ||
      Number(t.pages_count) > 0 || Number(t.records_count) > 0
    );
  }

  /** Whether the CURRENT format holds meaningful entered data — a selected
   *  status, a filled activity row, counts, remarks or a continuation — that
   *  a format switch would clear. Empty forms switch without ceremony. */
  function currentModeHasData(): boolean {
    const v = form.getValues();
    if (dayFormat === "split_day") {
      return (
        v.first_half.status !== undefined ||
        v.second_half.status !== undefined ||
        !!v.first_half.remarks.trim() ||
        !!v.second_half.remarks.trim() ||
        v.tasks.some((t) => t.day_part !== "full_day" && rowHasData(t))
      );
    }
    return (
      v.day_status !== undefined ||
      !!v.remarks.trim() ||
      v.tasks.some((t) => t.day_part === "full_day" && rowHasData(t))
    );
  }

  /** Tab handler: an empty format switches immediately; entered data asks
   *  for confirmation first (nothing is ever auto-converted). */
  function requestDayFormat(next: "full_day" | "split_day") {
    if (next === dayFormat) return;
    // Split Day has no additional-activity workflow, so a pending Full-Day
    // request would be stranded (unresolvable, and its approval would try to
    // add a second row the split rules forbid). Make the user resolve it first
    // rather than silently deleting their request.
    if (next === "split_day" && pendingRequest) {
      setFormError(
        "Resolve or dismiss the pending additional-activity request before switching to Split Day.",
      );
      return;
    }
    if (currentModeHasData()) {
      setPendingFormat(next);
    } else {
      switchDayFormat(next);
    }
  }

  // ── Second-activity approval flow ──────────────────────────────────────────
  // A period normally holds one activity. To add another, the employee fills an
  // extra activity section (revealed by "Add Activity") and sends it to the
  // project's PM as a request; it only becomes a real row once the PM approves.
  // `draftPart` marks that the LAST field-array row is that pending-to-be-
  // requested draft (and which period it belongs to), not a row that gets
  // saved with the report.
  const [draftPart, setDraftPart] = React.useState<DayPart | null>(null);

  const createActivityRequest = useCreateActivityRequest();
  const deleteActivityRequest = useDeleteActivityRequest();
  // The employee's own pending / rejected requests for this report (edit mode).
  const myRequests = useMyActivityRequests(reportId, mode === "edit");
  const pendingRequest = myRequests.data?.find((r) => r.status === "pending");
  const rejectedRequest = pendingRequest
    ? undefined
    : myRequests.data?.find((r) => r.status === "rejected");

  function isNoApprovalName(name?: string | null): boolean {
    const n = name?.trim().toUpperCase();
    return !!n && NO_APPROVAL_ACTIVITIES.has(n);
  }

  // Whether an activity row belongs to a routine parent Activity that doesn't
  // need PM approval (see NO_APPROVAL_ACTIVITIES).
  function rowIsNoApproval(row?: {
    activity_id?: string | null;
    sub_activity_id?: string | null;
  }): boolean {
    if (!row) return false;
    if (row.activity_id && isNoApprovalName(activityById.get(row.activity_id)?.name)) {
      return true;
    }
    if (
      row.sub_activity_id &&
      isNoApprovalName(subActivityById.get(row.sub_activity_id)?.activity_name)
    ) {
      return true;
    }
    return false;
  }

  // An additional activity needs PM approval only when BOTH it and the
  // period's first activity are outside NO_APPROVAL_ACTIVITIES.
  function secondActivityNeedsApproval(
    first?: { activity_id?: string | null; sub_activity_id?: string | null },
    second?: { activity_id?: string | null; sub_activity_id?: string | null },
  ): boolean {
    return !rowIsNoApproval(first) && !rowIsNoApproval(second);
  }

  /** The period's own primary activity — what the draft is compared against
   *  for the approval bypass. */
  function primaryRowOfDraftPeriod(
    values: WorkReportFormValues,
  ): WorkReportFormValues["tasks"][number] | undefined {
    const part = draftPart ?? "full_day";
    return values.tasks.find(
      (t, i) => t.day_part === part && i !== values.tasks.length - 1,
    );
  }

  // A quantity sub-activity (NUMERIC / NUMERIC_DAILY / TASK_WITH_QUANTITY) must
  // have its benchmarked count filled in — the same guard used on submit,
  // factored out so the "Request PM" path enforces it too.
  function validateBenchmarks(rows: WorkReportFormValues["tasks"]): boolean {
    let ok = true;
    rows.forEach((t, i) => {
      const sub = t.sub_activity_id ? subActivityById.get(t.sub_activity_id) : undefined;
      const countField = isQuantityBenchmark(sub?.benchmark_type)
        ? (sub!.relevant_count_field as RelevantCountField)
        : null;
      const key = countField ? countFieldName(countField) : null;
      if (key && Number(t[key] || 0) <= 0) {
        form.setError(`tasks.${i}.${key}`, {
          message: `Required — ${sub!.name} has a benchmark target`,
        });
        ok = false;
      }
    });
    if (!ok) setFormError("Fill in the required benchmark count(s) highlighted below.");
    return ok;
  }

  // "Request PM to Add This Activity" — the additional-activity draft (the
  // last row) is NOT saved to the report. The report is first persisted
  // without it, then the draft is sent to the PM as an activity request tagged
  // with its reporting period; on approval the PM's action turns it into a
  // real row in that period (see activity_requests).
  async function requestSecondActivity() {
    setFormError(null);
    const valid = await form.trigger();
    if (!valid) return;

    const values = form.getValues();
    const draft = values.tasks[values.tasks.length - 1];
    const realRows = values.tasks.slice(0, -1);
    if (!draft?.project_id || !draft?.sub_activity_id) {
      toast.error("Select a project, activity and sub-activity for the additional activity.");
      return;
    }
    // Validate benchmark counts on every row INCLUDING the draft being
    // requested, so a request can't be sent half-filled.
    if (!validateBenchmarks(values.tasks)) return;

    try {
      // Persist the report (without the draft) so the request can link to it.
      const persistValues = { ...values, tasks: realRows };
      const reportRow =
        mode === "create"
          ? await createMutation.mutateAsync(toCreateBody(persistValues))
          : await updateMutation.mutateAsync(toUpdateBody(persistValues));
      const savedReportId = mode === "create" ? reportRow.id : (reportId as string);

      await createActivityRequest.mutateAsync({
        report_id: savedReportId,
        // Activity requests are a FULL-DAY workflow only: this path is
        // unreachable in Split Day, so no period is ever targeted (the backend
        // rejects split-day requests outright).
        period_id: null,
        project_id: draft.project_id,
        activity_id: draft.activity_id || null,
        sub_activity_id: draft.sub_activity_id,
        // Each unit travels in its OWN field — a requested page count must never
        // be sent as docs_count.
        tags_count: Number(draft.tags_count) || 0,
        docs_count: Number(draft.docs_count) || 0,
        bom_count: Number(draft.bom_count) || 0,
        spares_count: Number(draft.spares_count) || 0,
        pages_count: Number(draft.pages_count) || 0,
        records_count: Number(draft.records_count) || 0,
      });
      toast.success(
        "Your request has been sent to your Project Manager for approval.",
      );

      if (mode === "create") {
        // Re-open the now-saved report so the Pending card renders in edit mode.
        router.push(`/work-reports/${savedReportId}/edit`);
      } else {
        setDraftPart(null);
        remove(values.tasks.length - 1);
      }
    } catch (err) {
      setFormError(
        err instanceof AppError ? err.message : "Could not send your request.",
      );
    }
  }

  async function dismissRejectedRequest() {
    if (!rejectedRequest) return;
    try {
      await deleteActivityRequest.mutateAsync(rejectedRequest.id);
    } catch (err) {
      toast.error(
        err instanceof AppError ? err.message : "Could not dismiss the request.",
      );
    }
  }

  // Reveal an empty additional-activity section for a period, marked as the
  // draft that must go through PM approval rather than a normal save.
  function addActivityDraft(part: DayPart) {
    append({ ...EMPTY_TASK_ROW, day_part: part });
    setDraftPart(part);
  }

  // Leave-type day statuses (week off / leave / company holiday / comp-off) in
  // FULL-DAY mode: the employee did no project work, so the activity editor is
  // frozen out — no rows, no benchmark, no pending — and only Remarks + Query
  // stay active. (Split mode handles this per half in ReportPeriodCard.)
  const dayStatus = form.watch("day_status");
  const noActivity = !isSplit && isNoActivityDayStatus(dayStatus);
  const prevNoActivity = React.useRef(noActivity);
  React.useEffect(() => {
    if (noActivity === prevNoActivity.current) return;
    prevNoActivity.current = noActivity;
    if (isSplit) return;
    if (noActivity) {
      // Drop activity rows + clear Office Location — none of it applies on leave.
      replace([]);
      form.setValue("location", undefined, { shouldValidate: true });
    } else if (form.getValues("tasks").length === 0) {
      // Switched back to a working day with no rows — restore one empty row.
      replace([{ ...EMPTY_TASK_ROW }]);
    }
  }, [noActivity, isSplit, replace, form]);

  // Split Day: a working half always shows exactly ONE activity editor, so the
  // row is created here rather than by an "Add Activity" button (there is
  // none). reconcileHalves only ever APPENDS into a working half that has no
  // row — it never deletes, never trims a malformed half back to one row and
  // never re-stamps a row's day_part — and returns the same array reference
  // when there is nothing to do, which is what keeps this idempotent across
  // re-renders. Clearing stays manual (Working -> Leave/Off confirmation).
  const firstHalfStatus = form.watch("first_half.status");
  const secondHalfStatus = form.watch("second_half.status");
  React.useEffect(() => {
    if (!isSplit) return;
    const rows = form.getValues("tasks");
    const next = reconcileHalves(
      rows,
      {
        first_half: firstHalfStatus !== undefined && !isNoActivityDayStatus(firstHalfStatus),
        second_half: secondHalfStatus !== undefined && !isNoActivityDayStatus(secondHalfStatus),
      },
      () => ({ ...EMPTY_TASK_ROW }),
    );
    if (next !== rows) replace(next as WorkReportFormValues["tasks"]);
  }, [isSplit, firstHalfStatus, secondHalfStatus, form, replace]);

  // Backfill the UI-only `activity_id` filter for rows loaded from the API
  // with a sub_activity_id already set (edit mode) — once the flat
  // sub-activity options arrive, resolve which Activity each belongs to so
  // the Sub-Activity select shows the right filtered list immediately.
  React.useEffect(() => {
    if (subActivityById.size === 0) return;
    fields.forEach((_, index) => {
      const row = form.getValues(`tasks.${index}`);
      // `fields` can be momentarily out of sync with form values (e.g. right
      // after the task rows are cleared for a leave-type day) — skip if so.
      if (!row) return;
      if (row.sub_activity_id && !row.activity_id) {
        const sub = subActivityById.get(row.sub_activity_id);
        if (sub) form.setValue(`tasks.${index}.activity_id`, sub.activity_id);
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [subActivityById, fields.length]);

  const createMutation = useCreateWorkReport();
  const updateMutation = useUpdateWorkReport(reportId ?? "");
  const isPending = createMutation.isPending || updateMutation.isPending;

  // ── Task continuation (feature-flagged, Full-Day only) ─────────────────────
  // Open work items the employee can continue in a report dated `reportDate`.
  // Split Day never continues tasks: no suggestions, no per-row Continue
  // prompts, and the open-tasks API is not called at all.
  const continuationEnabled = features.taskContinuation && !noActivity && !isSplit;
  const openTasksQuery = useOpenTasks(reportDate, {
    enabled: continuationEnabled && !!reportDate,
  });
  // Work items already added to this report — don't suggest them again.
  const addedWorkItemIds = React.useMemo(
    () => new Set((watchedTasks ?? []).map((t) => t.work_item_id).filter(Boolean)),
    [watchedTasks],
  );
  const openTasks = React.useMemo(
    () => (openTasksQuery.data?.items ?? []).filter((t) => !addedWorkItemIds.has(t.work_item_id)),
    [openTasksQuery.data, addedWorkItemIds],
  );
  // Open items keyed by "project_id|sub_activity_id" so a manual sub-activity
  // pick can offer an explicit Continue / Start-new choice for that exact task.
  const openBySubProject = React.useMemo(() => {
    const map = new Map<string, OpenTask>();
    for (const t of openTasksQuery.data?.items ?? []) {
      map.set(`${t.project_id}|${t.sub_activity_id}`, t);
    }
    return map;
  }, [openTasksQuery.data]);
  // Rows where the user chose "Start a new task" despite an open item existing —
  // suppresses the inline Continue/Start-new prompt for that row.
  const [startNewRows, setStartNewRows] = React.useState<Set<number>>(new Set());

  // Build a prefilled task row that continues an existing work item.
  const continuationRow = React.useCallback(
    (t: OpenTask) => ({
      ...EMPTY_TASK_ROW,
      project_id: t.project_id,
      project_name: t.project_name ?? undefined,
      project_code: t.project_code ?? undefined,
      activity_id: t.activity_id ?? "",
      activity_name: t.activity_name ?? undefined,
      sub_activity_id: t.sub_activity_id,
      sub_activity_name: t.sub_activity_name ?? undefined,
      work_item_id: t.work_item_id,
      work_item_lifecycle: t.lifecycle,
      started_date: t.started_on,
      due_date: t.due_date,
    }),
    [],
  );

  // "Continue in today's report" — fills the lone empty first row if untouched,
  // otherwise appends a new continuation row.
  const continueTask = React.useCallback(
    (t: OpenTask) => {
      const rows = form.getValues("tasks");
      const first = rows[0];
      const firstEmpty =
        rows.length === 1 && !first?.project_id && !first?.sub_activity_id;
      if (firstEmpty) {
        replace([continuationRow(t)]);
      } else {
        append(continuationRow(t));
      }
    },
    [append, replace, form, continuationRow],
  );

  // Attach an open work item to an existing row (manual "Continue existing").
  const attachToRow = React.useCallback(
    (index: number, t: OpenTask) => {
      form.setValue(`tasks.${index}.work_item_id`, t.work_item_id);
      form.setValue(`tasks.${index}.work_item_lifecycle`, t.lifecycle);
      form.setValue(`tasks.${index}.started_date`, t.started_on);
      form.setValue(`tasks.${index}.due_date`, t.due_date);
    },
    [form],
  );

  // Reset a row's Maintenance Plant selection (and its derived snapshots) —
  // called whenever the row's project changes, since the available plants are
  // scoped to the new project's Planning Plant.
  const clearRowPlant = React.useCallback(
    (index: number) => {
      form.setValue(`tasks.${index}.maintenance_plant_id`, "");
      form.setValue(`tasks.${index}.planning_plant_code`, undefined);
      form.setValue(`tasks.${index}.planning_plant_description`, undefined);
    },
    [form],
  );

  /** Row removal owns the draft bookkeeping (see addActivityDraft). */
  const removeRow = React.useCallback(
    (index: number) => {
      remove(index);
      // Removing the draft row (always the last) — or shrinking back to a
      // single activity — clears the pending-draft marker so the Add
      // Activity control comes back without a page refresh.
      if (draftPart !== null && index === fields.length - 1) {
        setDraftPart(null);
      } else if (fields.length - 1 <= 1) {
        setDraftPart(null);
      }
    },
    [remove, draftPart, fields.length],
  );

  const canRemove = React.useCallback(
    (index: number) => {
      if (isSplit) return true;
      return fields.length > 1 && index < fields.length;
    },
    [isSplit, fields.length],
  );

  // One report per employee per day: in create mode, look up whether the
  // selected date already has a report (backend also enforces this with a
  // unique constraint / 409). When one exists we surface a notice with a link
  // to open it, rather than letting the author create a duplicate.
  const existingForDate = useWorkReportList(
    {
      employee_id: employeeId ?? "",
      project_id: "",
      status: "",
      from: reportDate,
      to: reportDate,
      limit: 1,
      offset: 0,
    },
    { enabled: mode === "create" && !!employeeId && !!reportDate },
  );
  // Only trust a freshly-resolved result for the *current* date — never the
  // loading placeholder (which still holds the previous date's rows), so a date
  // with no report never trips the notice while its query is in flight.
  const existingReportForDate =
    mode === "create" && existingForDate.isSuccess && !existingForDate.isPlaceholderData
      ? existingForDate.data.items.find((r) => r.report_date === reportDate)
      : undefined;

  // Editable reports (draft / sent back / edit-granted) open straight in the
  // editor to add/edit activities; a locked report opens read-only, where the
  // author can still Request edit.
  const EDITABLE_STATUSES = ["draft", "rejected", "granted"];
  const pathForExisting = (r: { id: string; status: string }) =>
    EDITABLE_STATUSES.includes(r.status)
      ? `/work-reports/${r.id}/edit`
      : `/work-reports/${r.id}`;

  const tasksError = form.formState.errors.tasks?.message;

  async function onSubmit(values: WorkReportFormValues) {
    setFormError(null);

    // Decide what to do with an additional-activity draft (the last row) on
    // save: empty -> drop it; routine (no-approval) activity -> keep as a
    // normal row; anything else -> route through the PM request flow.
    let persist = values;
    if (draftPart !== null) {
      const draft = values.tasks[values.tasks.length - 1];
      if (!draft?.sub_activity_id) {
        persist = { ...values, tasks: values.tasks.slice(0, -1) };
      } else if (
        secondActivityNeedsApproval(primaryRowOfDraftPeriod(values), draft)
      ) {
        await requestSecondActivity();
        return;
      }
      // no-approval draft with a selection: fall through and save it as a row.
    }

    // A NUMERIC sub-activity's relevant_count_field is the benchmark's
    // actual-value source — it must be filled in whenever that benchmark
    // applies, so the deficit/productivity calc at submit time reflects real
    // production, not an unfilled field.
    if (!validateBenchmarks(persist.tasks)) return;

    try {
      const result =
        mode === "create"
          ? await createMutation.mutateAsync(toCreateBody(persist))
          : await updateMutation.mutateAsync(toUpdateBody(persist));
      toast.success(mode === "create" ? "Draft saved" : "Changes saved");
      router.push(`/work-reports/${result.id}`);
    } catch (error) {
      // Safety net: if the date was claimed between load and submit, the
      // backend returns 409 — open the existing report rather than dead-ending.
      if (mode === "create" && error instanceof AppError && error.status === 409) {
        const found = existingForDate.data?.items.find((r) => r.report_date === values.report_date);
        if (found) {
          toast.info(`A report for ${values.report_date} already exists — opening it.`);
          router.replace(pathForExisting(found));
          return;
        }
      }
      setFormError(
        error instanceof AppError ? error.message : "Something went wrong. Please try again.",
      );
    }
  }

  // Shared context for the reusable activity editor (Full Day + both halves).
  const editorCtx: ActivityEditorContext = {
    form,
    fields,
    watchedTasks,
    reportDate,
    projectOptions,
    projById,
    activityOptions,
    subActivityById,
    subActivityOptionsByActivity,
    continuationEnabled,
    openBySubProject,
    startNewRows,
    setStartNewRows,
    attachToRow,
    clearRowPlant,
    removeRow,
    canRemove,
  };

  // ── Split Day derived bits ─────────────────────────────────────────────────
  const firstHalf = form.watch("first_half");
  const secondHalf = form.watch("second_half");

  /** Daily summary for Split Day: fractions, activities, targets vs actuals. */
  const splitSummary = React.useMemo(() => {
    if (!isSplit) return null;
    const halves: Array<[HalfKey, typeof firstHalf]> = [
      ["first_half", firstHalf],
      ["second_half", secondHalf],
    ];
    let workingFraction = 0;
    let leaveFraction = 0;
    for (const [key, half] of halves) {
      if (half?.status === undefined) continue;
      if (isNoActivityDayStatus(half.status)) leaveFraction += DAY_PART_FRACTION[key];
      else workingFraction += DAY_PART_FRACTION[key];
    }
    let effectiveTarget = 0;
    let actualTotal = 0;
    let activityCount = 0;
    for (const t of watchedTasks ?? []) {
      if (t.day_part === "full_day") continue;
      if (!t.sub_activity_id) continue;
      activityCount += 1;
      const sub = subActivityById.get(t.sub_activity_id);
      const unit = isQuantityBenchmark(sub?.benchmark_type)
        ? (sub!.relevant_count_field as RelevantCountField)
        : null;
      if (unit && sub?.benchmark_value != null) {
        effectiveTarget += sub.benchmark_value * DAY_PART_FRACTION[t.day_part];
        actualTotal += Number(t[countFieldName(unit)] || 0);
      }
    }
    return { workingFraction, leaveFraction, activityCount, effectiveTarget, actualTotal };
  }, [isSplit, firstHalf, secondHalf, watchedTasks, subActivityById]);

  /** Approval-state slot (pending / rejected / draft request button) under the
   *  Full-Day rows. FULL DAY ONLY — Split Day has no additional-activity
   *  workflow, so its half cards never render this. */
  function approvalSlot(part: DayPart): React.ReactNode {
    if (isSplit) return null;
    const requestForPart = (r: ActivityRequest) =>
      part === "full_day"
        ? !r.day_part || r.day_part === "full_day"
        : r.day_part === part;
    if (pendingRequest && requestForPart(pendingRequest)) {
      return (
        <RequestStatusCard
          request={pendingRequest}
          activityNo={indicesOf(part).length + 1}
        />
      );
    }
    if (rejectedRequest && requestForPart(rejectedRequest)) {
      return (
        <RequestStatusCard
          request={rejectedRequest}
          activityNo={indicesOf(part).length + 1}
          onDismiss={() => void dismissRejectedRequest()}
          dismissing={deleteActivityRequest.isPending}
        />
      );
    }
    if (draftPart === part) {
      const values = form.getValues();
      const draft = values.tasks[values.tasks.length - 1];
      return secondActivityNeedsApproval(primaryRowOfDraftPeriod(values), draft) ? (
        <Button
          type="button"
          variant="secondary"
          loading={
            createActivityRequest.isPending ||
            createMutation.isPending ||
            updateMutation.isPending
          }
          onClick={() => void requestSecondActivity()}
        >
          <Send className="h-4 w-4" />
          Request Approval
        </Button>
      ) : (
        <p className="rounded-lg border border-dashed border-border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
          This activity does not need PM approval - it will be saved with
          the report when you save.
        </p>
      );
    }
    return null;
  }

  return (
    <Card>
      <CardContent className="pt-6">
        {formError && (
          <div
            role="alert"
            className="mb-4 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive"
          >
            {formError}
          </div>
        )}
        {existingReportForDate && (
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-md border border-primary/30 bg-primary/10 px-3 py-2 text-sm">
            <span>
              You already have a{" "}
              {existingReportForDate.status === "draft" ? "draft report" : "report"} for{" "}
              <span className="font-medium">{reportDate}</span>. Only one report per day is allowed —
              open it to add or edit activities.
            </span>
            <Button
              type="button"
              size="sm"
              onClick={() => router.push(pathForExisting(existingReportForDate))}
            >
              Open report
            </Button>
          </div>
        )}
        <Form {...form}>
          <form className="space-y-6" onSubmit={form.handleSubmit(onSubmit)} noValidate>

            {/* ── Employee (read-only) ── */}
            <div className="flex items-center gap-3 rounded-md border border-border bg-muted/40 px-3 py-2 text-sm">
              <span className="text-muted-foreground">Submitting as:</span>
              <span className="font-medium">{employeeName}</span>
            </div>

            {/* ── Day Format selector (feature-flagged) ── */}
            {splitEnabled && (
              <FormField
                control={form.control}
                name="day_format"
                render={() => (
                  <FormItem>
                    <FormLabel>Day Format</FormLabel>
                    <Tabs
                      items={[
                        { value: "full_day", label: "Full Day" },
                        { value: "split_day", label: "Split Day" },
                      ]}
                      value={dayFormat}
                      onChange={(v) => requestDayFormat(v as "full_day" | "split_day")}
                    />
                    <FormMessage />
                  </FormItem>
                )}
              />
            )}

            {/* ── Row 1 — one Location for the whole day, both modes.
                Full Day: Date | Day Status | Office Location.
                Split Day: Date | Office Location. ── */}
            <div className={isSplit ? "grid gap-4 sm:grid-cols-2" : "grid gap-4 sm:grid-cols-3"}>
              <FormField
                control={form.control}
                name="report_date"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>
                      Date <span className="text-destructive">*</span>
                    </FormLabel>
                    <FormControl>
                      <Input type="date" {...field} disabled={mode === "edit"} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              {!isSplit && (
                <FormField
                  control={form.control}
                  name="day_status"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>
                        Day Status <span className="text-destructive">*</span>
                      </FormLabel>
                      <Select
                        value={field.value ?? undefined}
                        onValueChange={(v) => field.onChange(v)}
                      >
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue placeholder="Select status" />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          {DAY_STATUSES.map((s) => (
                            <SelectItem key={s} value={s}>
                              {DAY_STATUS_LABEL[s]}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              )}
              <FormField
                control={form.control}
                name="location"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>
                      Office Location{" "}
                      {noActivity ? (
                        <span className="font-normal text-muted-foreground">(n/a)</span>
                      ) : (
                        <span className="text-destructive">*</span>
                      )}
                    </FormLabel>
                    <Select
                      value={field.value ?? undefined}
                      onValueChange={(v) => field.onChange(v)}
                      disabled={noActivity}
                    >
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="Select location" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {WORK_LOCATIONS.map((l) => (
                          <SelectItem key={l} value={l}>
                            {WORK_LOCATION_LABEL[l]}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <Separator />

            {/* ── Open tasks from previous reports (task continuation) ── */}
            {continuationEnabled && openTasks.length > 0 && !isSplit && (
              <div className="space-y-3">
                <div>
                  <h3 className="text-sm font-medium">Open tasks from previous reports</h3>
                  <p className="text-xs text-muted-foreground">
                    Continue one of these in today&apos;s report. The deadline stays
                    fixed - you can add today&apos;s work and mark the overall task
                    complete.
                  </p>
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  {openTasks.map((t) => (
                    <div
                      key={t.work_item_id}
                      className="flex flex-col gap-3 rounded-lg border border-border bg-muted/30 p-4"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className="truncate text-sm font-medium">
                            {t.project_name || t.project_code || "-"}
                          </p>
                          <p className="mt-0.5 truncate text-xs text-muted-foreground">
                            {`${t.activity_name ?? "-"} / ${t.sub_activity_name ?? "-"}`}
                          </p>
                        </div>
                        <Badge variant={LIFECYCLE_VARIANT[t.lifecycle] ?? "neutral"}>
                          {t.lifecycle === "OVERDUE" && t.days_overdue > 0
                            ? `Overdue ${t.days_overdue}d`
                            : LIFECYCLE_LABEL[t.lifecycle] ?? t.lifecycle}
                        </Badge>
                      </div>
                      <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
                        <span>Started {t.started_on}</span>
                        <span>Due {t.due_date}</span>
                      </div>
                      <Button
                        type="button"
                        size="sm"
                        variant="secondary"
                        className="self-start"
                        onClick={() => continueTask(t)}
                      >
                        <ArrowRight className="h-4 w-4" />
                        Continue in today&apos;s report
                      </Button>
                    </div>
                  ))}
                </div>
                <Separator />
              </div>
            )}

            {isSplit ? (
              /* ── Split Day: two reusable period cards, stacked vertically —
                  First Half is one full-width row, Second Half the next, on
                  every breakpoint (never two columns: long project /
                  activity / sub-activity names need the full content width). ── */
              <div className="space-y-4">
                <div className="grid grid-cols-1 gap-6">
                  <ReportPeriodCard
                    partKey="first_half"
                    ctx={editorCtx}
                    indices={indicesOf("first_half")}
                    onClearActivities={() => clearHalfRows("first_half")}
                  />
                  <ReportPeriodCard
                    partKey="second_half"
                    ctx={editorCtx}
                    indices={indicesOf("second_half")}
                    onClearActivities={() => clearHalfRows("second_half")}
                  />
                </div>

                {tasksError && (
                  <p className="text-xs font-medium text-destructive">{tasksError}</p>
                )}

                {/* Daily summary: fractions + activities + target vs actual. */}
                {splitSummary && (
                  <div className="flex flex-wrap gap-x-6 gap-y-2 rounded-md border border-border bg-muted/30 px-4 py-3 text-sm">
                    <span>
                      Working:{" "}
                      <span className="font-medium">
                        {Math.round(splitSummary.workingFraction * 100)}%
                      </span>
                    </span>
                    <span>
                      Leave/Off:{" "}
                      <span className="font-medium">
                        {Math.round(splitSummary.leaveFraction * 100)}%
                      </span>
                    </span>
                    <span>
                      Activities:{" "}
                      <span className="font-medium">{splitSummary.activityCount}</span>
                    </span>
                    <span>
                      Effective target:{" "}
                      <span className="font-medium">
                        {formatInt(splitSummary.effectiveTarget)}
                      </span>
                    </span>
                    <span>
                      Actual total:{" "}
                      <span className="font-medium">
                        {formatInt(splitSummary.actualTotal)}
                      </span>
                    </span>
                  </div>
                )}
              </div>
            ) : (
              /* ── Full Day: the classic experience, unchanged ── */
              <div className="space-y-3">
                <h3 className="text-sm font-medium">Project activities</h3>

                {noActivity ? (
                  <div className="rounded-lg border border-dashed border-border bg-muted/40 p-4 text-sm text-muted-foreground">
                    <p className="font-medium text-foreground">
                      No project activities for this day
                    </p>
                    <p className="mt-1">
                      You selected{" "}
                      <span className="font-medium">
                        {dayStatus ? DAY_STATUS_LABEL[dayStatus] : ""}
                      </span>{" "}
                      - you&apos;re off, so activities, benchmarks and pending tracking
                      don&apos;t apply. Add any Remarks or a Query below if needed.
                    </p>
                  </div>
                ) : (
                  <>
                    <PeriodActivityEditor
                      ctx={editorCtx}
                      indices={fields.map((_, i) => i)}
                      fraction={dayStatus === "half_day" ? 0.5 : 1}
                    />

                    {tasksError && (
                      <p className="text-xs font-medium text-destructive">{tasksError}</p>
                    )}

                    {/* Additional-activity flow: routine ones save directly;
                        any other second activity goes through PM approval. */}
                    {approvalSlot("full_day") ??
                      (fields.length >= 1 ? (
                        <Button
                          type="button"
                          variant="secondary"
                          onClick={() => addActivityDraft("full_day")}
                        >
                          <Plus className="h-4 w-4" />
                          Add Activity
                        </Button>
                      ) : null)}
                  </>
                )}
              </div>
            )}

            <Separator />

            {/* ── Day Remarks — one remark for the whole day (not per activity).
                Full Day only: a Split Day report keeps its remarks per half
                (inside each period card), never a third overall field. ── */}
            {!isSplit && (
              <>
                <FormField
                  control={form.control}
                  name="remarks"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>
                        Day Remarks{" "}
                        <span className="font-normal text-muted-foreground">(optional)</span>
                      </FormLabel>
                      <FormControl>
                        <Textarea
                          rows={3}
                          placeholder="What did you work on today?"
                          {...field}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <Separator />
              </>
            )}

            {/* ── Query / Issues (end) ── */}
            <FormField
              control={form.control}
              name="query_text"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>
                    Query / Issues{" "}
                    <span className="font-normal text-muted-foreground">(optional)</span>
                  </FormLabel>
                  <FormControl>
                    <Textarea
                      rows={3}
                      placeholder="Any blockers or questions?"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <div className="flex justify-end gap-2 pt-2">
              <Button
                type="button"
                variant="ghost"
                onClick={() => router.back()}
                disabled={isPending}
              >
                Cancel
              </Button>
              <Button type="submit" loading={isPending} disabled={!!existingReportForDate}>
                {mode === "create" ? "Save Draft" : "Save changes"}
              </Button>
            </div>
          </form>
        </Form>

        {/* Day-format switch confirmation — shown whenever the current format
            holds entered data. Cancel keeps the current format with
            everything intact; confirming clears the current format's state
            and starts the other format blank (nothing is auto-converted). */}
        <AlertDialog
          open={pendingFormat !== null}
          onOpenChange={(open) => {
            if (!open) setPendingFormat(null);
          }}
        >
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Change Day Format?</AlertDialogTitle>
              <AlertDialogDescription>
                Changing the format will clear the activities, statuses and
                remarks entered for the current format. The system will not
                automatically assign them to another half or combine them.
                Your Date, Office Location and Query / Issues are kept.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel onClick={() => setPendingFormat(null)}>
                Cancel
              </AlertDialogCancel>
              <AlertDialogAction
                onClick={() => {
                  if (pendingFormat) switchDayFormat(pendingFormat);
                  setPendingFormat(null);
                }}
              >
                Change format
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </CardContent>
    </Card>
  );

  /** Remove every task row of a half (Working -> Leave/Off confirmation
   *  already happened inside the period card). The other half and any
   *  full_day rows are left untouched. */
  function clearHalfRows(part: HalfKey) {
    const rows = form.getValues("tasks");
    const kept = clearHalf(rows, part);
    if (kept !== rows) replace(kept as WorkReportFormValues["tasks"]);
  }
}

/**
 * Read-only card standing in for an additional activity that is waiting on the
 * PM. `Pending PM Approval` while the request is pending; `Rejected` (with a
 * Dismiss button) once the PM declines, after which the employee can request
 * again.
 */
function RequestStatusCard({
  request,
  activityNo,
  onDismiss,
  dismissing,
}: {
  request: ActivityRequest;
  activityNo: number;
  onDismiss?: () => void;
  dismissing?: boolean;
}) {
  const isRejected = request.status === "rejected";
  return (
    <div className="space-y-3 rounded-lg border border-dashed border-border bg-muted/30 p-4">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-medium">
          Activity {activityNo}
          {request.day_part && request.day_part !== "full_day" && (
            <span className="ml-2 text-xs font-normal text-muted-foreground">
              ({DAY_PART_LABEL[request.day_part as DayPart]})
            </span>
          )}
        </h4>
        <Badge variant={isRejected ? "danger" : "warning"}>
          {isRejected ? "Rejected" : "Pending PM Approval"}
        </Badge>
      </div>
      <dl className="grid grid-cols-1 gap-x-4 gap-y-2 text-sm sm:grid-cols-3">
        <div>
          <dt className="text-xs text-muted-foreground">Project</dt>
          <dd className="font-medium">
            {request.project_name || request.project_code || "—"}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">Activity</dt>
          <dd className="font-medium">{request.activity_name ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">Sub Activity</dt>
          <dd className="font-medium">{request.sub_activity_name || "—"}</dd>
        </div>
      </dl>
      {isRejected ? (
        <div className="flex items-center justify-between gap-3">
          <p className="text-xs text-muted-foreground">
            Your Project Manager declined this activity. Dismiss it to request a
            different one.
          </p>
          {onDismiss && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              loading={dismissing}
              onClick={onDismiss}
            >
              <Trash2 className="h-4 w-4" />
              Dismiss
            </Button>
          )}
        </div>
      ) : (
        <p className="text-xs text-muted-foreground">
          Waiting for your Project Manager to approve this activity. No further
          activities can be added until it&apos;s decided.
        </p>
      )}
    </div>
  );
}
