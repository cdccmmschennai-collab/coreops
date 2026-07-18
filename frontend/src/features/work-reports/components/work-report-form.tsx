"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { zodResolver } from "@hookform/resolvers/zod";
import { useFieldArray, useForm, type Control } from "react-hook-form";
import { ArrowRight, Plus, Send, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";
import { useActivities, useSubActivityOptions } from "@/features/activity-master/hooks";
import {
  COUNT_FIELD_KEY,
  COUNT_FIELD_LABEL,
  isQuantityBenchmark,
  isTaskBenchmark,
  type RelevantCountField,
} from "@/features/activity-master/types";
import {
  useCreateActivityRequest,
  useDeleteActivityRequest,
  useMyActivityRequests,
} from "@/features/activity-requests/hooks";
import type { ActivityRequest } from "@/features/activity-requests/types";
import { useAuth } from "@/features/auth/auth-provider";
import { useMaintenancePlantOptions } from "@/features/plant-master/hooks";
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
  DAY_STATUS_LABEL,
  DAY_STATUSES,
  EMPTY_TASK_ROW,
  WORK_LOCATION_LABEL,
  WORK_LOCATIONS,
  isNoActivityDayStatus,
  toCreateBody,
  toUpdateBody,
  workReportFormSchema,
  type WorkReportFormValues,
} from "../schemas";

interface WorkReportFormProps {
  mode: "create" | "edit";
  defaultValues: WorkReportFormValues;
  reportId?: string;
}

// COUNT_FIELD_KEY / COUNT_FIELD_LABEL are imported from activity-master/types:
// one declaration of the six units, mirroring the backend's COUNT_FIELD_BY_UNIT.

/** The form field name for a unit, typed against the task row's count fields. */
type CountFieldName =
  | "tags_count" | "docs_count" | "bom_count"
  | "spares_count" | "pages_count" | "records_count";

const countFieldName = (u: RelevantCountField): CountFieldName =>
  COUNT_FIELD_KEY[u] as CountFieldName;

const ALL_COUNT_FIELDS: CountFieldName[] = [
  "tags_count", "docs_count", "bom_count",
  "spares_count", "pages_count", "records_count",
];

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

// Human labels + badge tone for a work item's derived lifecycle.
const LIFECYCLE_LABEL: Record<string, string> = {
  IN_PROGRESS: "In progress",
  DUE_TODAY: "Due today",
  OVERDUE: "Overdue",
  COMPLETED_ON_TIME: "Completed",
  COMPLETED_LATE: "Completed late",
};
const LIFECYCLE_VARIANT: Record<string, "neutral" | "warning" | "danger" | "success"> = {
  IN_PROGRESS: "neutral",
  DUE_TODAY: "warning",
  OVERDUE: "danger",
  COMPLETED_ON_TIME: "success",
  COMPLETED_LATE: "warning",
};

/** "2026-06-16" + 2 -> "2026-06-18". Client-side preview only, for a
 * TASK_BASED row that hasn't been saved yet — the server is authoritative
 * once the row exists (it computes due_date the same way, on save). */
function addDays(isoDate: string, days: number): string | null {
  const d = new Date(`${isoDate}T00:00:00`);
  if (Number.isNaN(d.getTime())) return null;
  d.setDate(d.getDate() + days);
  // Format from local parts (not toISOString, which would shift the day by the
  // UTC offset and land a day early in IST).
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

const MONTH_ABBR = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

/** "2026-07-18" -> "18 Jul 2026". Parsed from the string's own parts rather
 *  than via Date, which would shift the day by the UTC offset in IST. */
function formatDueDate(isoDate: string | null | undefined): string | null {
  if (!isoDate) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(isoDate);
  if (!m) return null;
  const month = MONTH_ABBR[Number(m[2]) - 1];
  if (!month) return null;
  return `${Number(m[3])} ${month} ${m[1]}`;
}

/** Words that carry no instruction of their own — they only glue a period or a
 *  target together ("COMPLETE IN 1 DAY", "500 REQUIRED PAGES/DAY"). */
const FILLER_REMARK_WORDS = new Set([
  "COMPLETE", "COMPLETED", "COMPLETION", "FINISH", "WITHIN", "IN", "PER", "A",
  "AN", "OF", "TARGET", "REQUIRED", "REQUIREMENT", "MINIMUM", "MIN", "DAY",
  "DAYS", "DAILY", "EVERY", "AND", "THE", "IS", "TO", "BE",
]);

/**
 * True when benchmark_remarks says nothing the structured fields do not already
 * say - "1DAY" beside a 1-day period, or "500 REQUIRED PAGES/DAY" beside a
 * target of 500 PAGES. Such remarks are dropped rather than repeated under a
 * "Note:" line.
 *
 * Case and whitespace are normalised for the COMPARISON ONLY; the stored
 * Activity Master value is never touched, and a remark with any leftover
 * meaningful word is always shown verbatim.
 */
function isDuplicateRemark(
  remarks: string,
  periodDays: number | null | undefined,
  benchmarkValue: number | null | undefined,
  unit: RelevantCountField | null | undefined,
): boolean {
  const tokens = remarks
    .toUpperCase()
    // "1DAY" carries no separator, so split digit/letter runs apart first.
    .replace(/(\d)([A-Z])/g, "$1 $2")
    .replace(/([A-Z])(\d)/g, "$1 $2")
    .split(/[^A-Z0-9.]+/)
    .filter(Boolean);
  if (!tokens.length) return true;

  const unitWords = unit
    ? new Set([
        COUNT_FIELD_LABEL[unit].toUpperCase(),
        // "PAGES" configured, "PAGE" written (or the reverse).
        COUNT_FIELD_LABEL[unit].toUpperCase().replace(/S$/, ""),
        `${COUNT_FIELD_LABEL[unit].toUpperCase()}S`,
      ])
    : new Set<string>();

  return tokens.every((raw) => {
    const token = raw.replace(/\.$/, "");
    if (!token) return true;
    if (FILLER_REMARK_WORDS.has(token)) return true;
    if (unitWords.has(token)) return true;
    const num = Number(token);
    if (!Number.isNaN(num)) {
      return num === periodDays || num === benchmarkValue;
    }
    return false;
  });
}

/**
 * Maintenance Plant picker for one task row. The options are scoped to the
 * selected project's Planning Plant — the dropdown reloads (a fresh,
 * planning-plant-filtered fetch) whenever that code changes, so a user never
 * sees Maintenance Plants from other Planning Plants. Planning Plant +
 * Description (PP) are determined by the project and shown read-only.
 */
function MaintenancePlantField({
  control,
  index,
  planningPlantCode,
  planningPlantDescription,
}: {
  control: Control<WorkReportFormValues>;
  index: number;
  planningPlantCode?: string;
  planningPlantDescription?: string;
}) {
  const hasPlanningPlant = !!planningPlantCode;
  const { options, isLoading } = useMaintenancePlantOptions(
    true,
    planningPlantCode,
    hasPlanningPlant,
  );

  return (
    <>
      <FormField
        control={control}
        name={`tasks.${index}.maintenance_plant_id`}
        render={({ field: f }) => (
          <FormItem className="min-w-0">
            <FormLabel className="block text-xs font-medium leading-none text-muted-foreground">
              Maintenance Plant
            </FormLabel>
            <FormControl>
              <Combobox
                value={f.value || ""}
                onValueChange={f.onChange}
                options={options}
                placeholder={
                  hasPlanningPlant
                    ? isLoading
                      ? "Loading plants…"
                      : "Select plant…"
                    : "Select a project first"
                }
                searchPlaceholder="Search maintenance plants…"
                emptyMessage="No plants for this Planning Plant."
                disabled={!hasPlanningPlant}
              />
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />
      <div className="space-y-2">
        <span className="block text-xs font-medium leading-none text-muted-foreground">
          Planning Plant
        </span>
        <div className="flex h-9 items-center rounded-md border border-input bg-muted/40 px-3 font-mono text-sm text-muted-foreground">
          {planningPlantCode ?? "—"}
        </div>
      </div>
      <div className="space-y-2">
        <span className="block text-xs font-medium leading-none text-muted-foreground">
          Description (PP)
        </span>
        <div className="flex h-9 items-center truncate rounded-md border border-input bg-muted/40 px-3 text-sm text-muted-foreground">
          {planningPlantDescription ?? "—"}
        </div>
      </div>
    </>
  );
}

/**
 * Read-only card standing in for a second activity that is waiting on the PM.
 * `Pending PM Approval` while the request is pending; `Rejected` (with a Dismiss
 * button) once the PM declines, after which the employee can request again.
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
        <h4 className="text-sm font-medium">Activity {activityNo}</h4>
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

  // ── Second-activity approval flow ──────────────────────────────────────────
  // The report normally holds one activity. To add a second, the employee fills
  // an extra activity section (revealed by "Add Activity", exactly as today) and
  // sends it to the project's PM as a request; it only becomes a real row once
  // the PM approves. `secondDraft` marks that the last field-array row is that
  // pending-to-be-requested draft, not a row that gets saved with the report.
  const [secondDraft, setSecondDraft] = React.useState(false);

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
  // need PM approval (see NO_APPROVAL_ACTIVITIES). Keyed off the parent Activity
  // selection (activity_id) so it applies the moment the Activity is chosen -
  // before a sub-activity is picked, and to any new sub-activities added later -
  // with a fallback to the sub-activity's own parent (edit-mode rows).
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

  // A second activity needs PM approval only when BOTH it and the day's first
  // activity are outside NO_APPROVAL_ACTIVITIES. If either the first activity
  // OR the second one is a routine activity (meeting / training / trainer), the
  // second saves straight onto the report with no approval.
  function secondActivityNeedsApproval(
    first?: { activity_id?: string | null; sub_activity_id?: string | null },
    second?: { activity_id?: string | null; sub_activity_id?: string | null },
  ): boolean {
    return !rowIsNoApproval(first) && !rowIsNoApproval(second);
  }

  // A quantity sub-activity (NUMERIC / NUMERIC_DAILY / TASK_WITH_QUANTITY) must
  // have its benchmarked count filled in — the same guard used on submit,
  // factored out so the "Request PM" path enforces it too.
  function validateBenchmarks(rows: WorkReportFormValues["tasks"]): boolean {
    let ok = true;
    rows.forEach((t, i) => {
      const sub = t.sub_activity_id ? subActivityById.get(t.sub_activity_id) : undefined;
      const countField = isQuantityBenchmark(sub?.benchmark_type)
        ? sub!.relevant_count_field
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

  // "Request PM to Add This Activity" — the second-activity draft (the last row)
  // is NOT saved to the report. The report is first persisted with its first
  // activity, then the draft is sent to the PM as an activity request. On
  // approval the PM's action turns it into a real row (see activity_requests).
  async function requestSecondActivity() {
    setFormError(null);
    const valid = await form.trigger();
    if (!valid) return;

    const values = form.getValues();
    const draft = values.tasks[values.tasks.length - 1];
    const realRows = values.tasks.slice(0, -1);
    if (!draft?.project_id || !draft?.sub_activity_id) {
      toast.error("Select a project, activity and sub-activity for the second activity.");
      return;
    }
    // Validate benchmark counts on every row INCLUDING the draft being requested,
    // so a request can't be sent with the requested activity's required fields
    // (e.g. benchmark count) left blank.
    if (!validateBenchmarks(values.tasks)) return;

    try {
      // Persist the report (first activity only) so the request can link to it.
      const persistValues = { ...values, tasks: realRows };
      const reportRow =
        mode === "create"
          ? await createMutation.mutateAsync(toCreateBody(persistValues))
          : await updateMutation.mutateAsync(toUpdateBody(persistValues));
      const savedReportId = mode === "create" ? reportRow.id : (reportId as string);

      await createActivityRequest.mutateAsync({
        report_id: savedReportId,
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
        setSecondDraft(false);
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

  // Reveal an empty second-activity section (same UI as today's append), marked
  // as the draft that must go through PM approval rather than a normal save.
  function addSecondActivityDraft() {
    append({ ...EMPTY_TASK_ROW });
    setSecondDraft(true);
  }

  // Leave-type day statuses (week off / leave / company holiday / comp-off):
  // the employee did no project work, so the activity editor is frozen out —
  // no rows, no benchmark, no pending — and only Remarks + Query stay active.
  const dayStatus = form.watch("day_status");
  const noActivity = isNoActivityDayStatus(dayStatus);
  const prevNoActivity = React.useRef(noActivity);
  React.useEffect(() => {
    if (noActivity === prevNoActivity.current) return;
    prevNoActivity.current = noActivity;
    if (noActivity) {
      // Drop activity rows + clear Office Location — none of it applies on leave.
      replace([]);
      form.setValue("location", undefined, { shouldValidate: true });
    } else if (form.getValues("tasks").length === 0) {
      // Switched back to a working day with no rows — restore one empty row.
      replace([{ ...EMPTY_TASK_ROW }]);
    }
  }, [noActivity, replace, form]);

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

  const watchedTasks = form.watch("tasks");
  const reportDate = form.watch("report_date");

  // ── Task continuation (feature-flagged) ────────────────────────────────────
  // Open work items the employee can continue in a report dated `reportDate`.
  const continuationEnabled = features.taskContinuation && !noActivity;
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

    // Decide what to do with a second-activity draft (the last row) on save:
    //  - empty (no sub-activity picked)  -> drop it, save the rest;
    //  - no-approval activity (meeting / training) -> keep it as a normal row;
    //  - any other activity -> it needs PM approval, so route through the
    //    request flow (which preserves it as Pending) instead of discarding it.
    let persist = values;
    if (secondDraft) {
      const draft = values.tasks[values.tasks.length - 1];
      if (!draft?.sub_activity_id) {
        persist = { ...values, tasks: values.tasks.slice(0, -1) };
      } else if (
        secondActivityNeedsApproval(values.tasks[0], draft)
      ) {
        await requestSecondActivity();
        return;
      }
      // no-approval draft with a selection: fall through and save it as a row.
    }

    // A NUMERIC sub-activity's relevant_count_field is the benchmark's
    // actual-value source — it must be filled in (not left at the default
    // 0) whenever that benchmark applies, so the deficit/productivity calc
    // at submit time reflects real production, not an unfilled field.
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

            {/* ── Row 1: Date, Day Status, Location ── */}
            <div className="grid gap-4 sm:grid-cols-3">
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
            {continuationEnabled && openTasks.length > 0 && (
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

            {/* ── Project Task Rows ── */}
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
              {fields.map((field, index) => {
                const selectedProjectId = watchedTasks?.[index]?.project_id;
                const selectedProject = selectedProjectId
                  ? projById.get(selectedProjectId)
                  : undefined;
                // Prefer the live RBAC-scoped project; fall back to the task snapshot
                // (edit mode where the project is archived / no longer accessible).
                const projectCodeLabel =
                  selectedProject?.code ?? watchedTasks?.[index]?.project_code ?? "—";
                const jobCodeLabel = selectedProject?.job_code_code ?? "—";

                // Task continuation, per row.
                const rowSubId = watchedTasks?.[index]?.sub_activity_id;
                const rowWorkItemId = watchedTasks?.[index]?.work_item_id;
                const rowLifecycle = watchedTasks?.[index]?.work_item_lifecycle;
                const rowStarted = watchedTasks?.[index]?.started_date;
                const isContinuation = continuationEnabled && !!rowWorkItemId;
                // A manual sub-activity pick that matches an open work item ->
                // offer an explicit Continue existing / Start a new task choice
                // (unless already linked or the user chose Start-new for this row).
                const rowOpenMatch =
                  continuationEnabled && !rowWorkItemId && selectedProjectId && rowSubId
                    ? openBySubProject.get(`${selectedProjectId}|${rowSubId}`)
                    : undefined;

                return (
                  <div
                    key={field.id}
                    className="space-y-5 rounded-lg border border-border p-4"
                  >
                    {/* Row remove control. */}
                    <div className="flex items-end justify-end gap-2">
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        onClick={() => {
                          remove(index);
                          // "Add Activity" only shows when there's no pending
                          // second-activity draft. Once a delete leaves a single
                          // row (whichever row was removed), that row is just the
                          // first activity again — clear the draft flag so the
                          // button comes back without needing a page refresh.
                          if (fields.length - 1 <= 1) {
                            setSecondDraft(false);
                          }
                        }}
                        disabled={fields.length === 1}
                        aria-label="Remove activity"
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>

                    {/* Continuation banner: this row continues an existing work
                        item. Project/Activity/Sub are locked (the backend forbids
                        changing them on a continuation). */}
                    {isContinuation && (
                      <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-primary/30 bg-primary/10 px-3 py-2 text-sm">
                        <span>
                          Continuing task started on{" "}
                          <span className="font-medium">{rowStarted ?? "—"}</span>
                          {watchedTasks?.[index]?.due_date && (
                            <> · due {watchedTasks[index].due_date}</>
                          )}
                        </span>
                        {rowLifecycle && (
                          <Badge variant={LIFECYCLE_VARIANT[rowLifecycle] ?? "neutral"}>
                            {LIFECYCLE_LABEL[rowLifecycle] ?? rowLifecycle}
                          </Badge>
                        )}
                      </div>
                    )}

                    {/* Manual pick matched an open work item: explicit choice. */}
                    {rowOpenMatch && !startNewRows.has(index) && (
                      <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-dashed border-border bg-muted/30 px-3 py-2 text-sm">
                        <span className="text-muted-foreground">
                          You have an open task for this activity (started{" "}
                          {rowOpenMatch.started_on}, due {rowOpenMatch.due_date}).
                        </span>
                        <div className="flex items-center gap-2">
                          <Button
                            type="button"
                            size="sm"
                            variant="secondary"
                            onClick={() => attachToRow(index, rowOpenMatch)}
                          >
                            Continue existing task
                          </Button>
                          <Button
                            type="button"
                            size="sm"
                            variant="ghost"
                            onClick={() =>
                              setStartNewRows((prev) => new Set(prev).add(index))
                            }
                          >
                            Start a new task
                          </Button>
                        </div>
                      </div>
                    )}

                    {/* Row A — Project Name | Project Code | Job Code.
                        Project Code / Job Code are read-only, auto-filled from the
                        selected project. */}
                    <div className="grid grid-cols-1 items-start gap-4 md:grid-cols-[minmax(0,1.4fr)_120px_120px]">

                      {/* Project Name — searchable combobox (name + code) */}
                      <FormField
                        control={form.control}
                        name={`tasks.${index}.project_id`}
                        render={({ field: f }) => (
                          <FormItem className="min-w-0">
                            <FormLabel className="block text-xs leading-none text-muted-foreground">
                              Project Name <span className="text-destructive">*</span>
                            </FormLabel>
                            <FormControl>
                              <Combobox
                                value={f.value}
                                onValueChange={(v) => {
                                  const changed = v !== f.value;
                                  f.onChange(v);
                                  // Maintenance Plant options depend on the project's
                                  // Planning Plant — clear any prior selection so a
                                  // plant from the old Planning Plant can't linger.
                                  if (changed) clearRowPlant(index);
                                }}
                                options={projectOptions}
                                placeholder="Select project…"
                                searchPlaceholder="Search by name or code…"
                                emptyMessage="No matching projects."
                                allowClear={false}
                                disabled={isContinuation}
                              />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />

                      {/* Project Code — read-only metadata, auto-filled from selection */}
                      <div className="space-y-2">
                        <span className="block text-xs font-medium leading-none text-muted-foreground">
                          Project Code
                        </span>
                        <div className="flex h-9 items-center rounded-md border border-input bg-muted/40 px-3 font-mono text-sm text-muted-foreground">
                          {projectCodeLabel}
                        </div>
                      </div>

                      {/* Job Code — read-only metadata, auto-filled from selection */}
                      <div className="space-y-2">
                        <span className="block text-xs font-medium leading-none text-muted-foreground">
                          Job Code
                        </span>
                        <div className="flex h-9 items-center rounded-md border border-input bg-muted/40 px-3 font-mono text-sm text-muted-foreground">
                          {jobCodeLabel}
                        </div>
                      </div>

                    </div>

                    {/* Row A2: Maintenance Plant — scoped to the selected project's
                        Planning Plant (the dropdown refetches when the project's
                        Planning Plant changes; a user never sees plants from other
                        Planning Plants). Planning Plant + Description (PP) are
                        determined by the project and shown read-only. Maintenance
                        Plant lines up under Project Name, Planning Plant under
                        Project Code, Description (PP) spans the remaining width. */}
                    <div className="grid grid-cols-1 items-start gap-4 md:grid-cols-[minmax(0,1.4fr)_120px_minmax(0,1fr)]">
                      <MaintenancePlantField
                        control={form.control}
                        index={index}
                        planningPlantCode={
                          selectedProject?.planning_plant_code
                          ?? watchedTasks?.[index]?.planning_plant_code
                          ?? undefined
                        }
                        planningPlantDescription={
                          selectedProject?.planning_plant_description
                          ?? watchedTasks?.[index]?.planning_plant_description
                          ?? undefined
                        }
                      />
                    </div>

                    {/* Row B: Activity (25%) | Sub-Activity (75%) — own full-width row
                        so long sub-activity names show in full, uncramped. Selections
                        come from the Activity Master (Settings → Activity Master),
                        never hardcoded here. */}
                    <div className="grid grid-cols-[1fr_3fr] gap-4">
                      <FormField
                        control={form.control}
                        name={`tasks.${index}.activity_id`}
                        render={({ field: f }) => (
                          <FormItem className="min-w-0">
                            <FormLabel className="block text-xs leading-none text-muted-foreground">
                              Activity <span className="text-destructive">*</span>
                            </FormLabel>
                            <FormControl>
                              <Combobox
                                value={f.value || ""}
                                onValueChange={(v) => {
                                  f.onChange(v);
                                  // Changing the Activity invalidates any previously
                                  // chosen Sub-Activity from a different Activity.
                                  const currentSub = form.getValues(`tasks.${index}.sub_activity_id`);
                                  if (currentSub && subActivityById.get(currentSub)?.activity_id !== v) {
                                    form.setValue(`tasks.${index}.sub_activity_id`, "");
                                    form.setValue(`tasks.${index}.sub_activity_name`, undefined);
                                    form.setValue(`tasks.${index}.activity_name`, undefined);
                                  }
                                }}
                                options={activityOptions}
                                placeholder="Select activity…"
                                searchPlaceholder="Search activities…"
                                emptyMessage="No matching activities."
                                disabled={isContinuation}
                              />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                      <FormField
                        control={form.control}
                        name={`tasks.${index}.sub_activity_id`}
                        render={({ field: f }) => {
                          const selectedActivityId = watchedTasks?.[index]?.activity_id;
                          const options = selectedActivityId
                            ? subActivityOptionsByActivity.get(selectedActivityId) ?? []
                            : [];
                          return (
                            <FormItem className="min-w-0">
                              <FormLabel className="block text-xs leading-none text-muted-foreground">
                                Sub-Activity <span className="text-destructive">*</span>
                              </FormLabel>
                              <FormControl>
                                <Combobox
                                  value={f.value || ""}
                                  onValueChange={(v) => {
                                    const prev = form.getValues(
                                      `tasks.${index}.sub_activity_id`,
                                    );
                                    f.onChange(v);
                                    const sub = v ? subActivityById.get(v) : undefined;
                                    form.setValue(`tasks.${index}.sub_activity_name`, sub?.name);
                                    form.setValue(`tasks.${index}.activity_name`, sub?.activity_name);
                                    // Server derives activity_type from the new selection.
                                    form.setValue(`tasks.${index}.activity_type`, "");
                                    // Clear the OLD sub-activity's benchmarked count
                                    // when the selection actually changes: 200 typed
                                    // against a DOCS activity must not silently
                                    // survive as docs_count once the row is switched
                                    // to a PAGES one. Only the previous unit's field
                                    // is reset — counts the employee entered for
                                    // other units are left alone, and the new unit's
                                    // own field is never wiped (it may be being
                                    // re-selected on an edit).
                                    if (prev && prev !== v) {
                                      const prevSub = subActivityById.get(prev);
                                      const prevUnit = isQuantityBenchmark(
                                        prevSub?.benchmark_type,
                                      )
                                        ? prevSub!.relevant_count_field
                                        : null;
                                      const newUnit = isQuantityBenchmark(sub?.benchmark_type)
                                        ? sub!.relevant_count_field
                                        : null;
                                      if (prevUnit && prevUnit !== newUnit) {
                                        form.setValue(
                                          `tasks.${index}.${countFieldName(prevUnit)}`,
                                          "0",
                                        );
                                      }
                                    }
                                  }}
                                  options={options}
                                  placeholder={selectedActivityId ? "Select sub-activity…" : "Pick an Activity first"}
                                  searchPlaceholder="Search sub-activities…"
                                  emptyMessage="No matching sub-activities."
                                  disabled={!selectedActivityId || isContinuation}
                                />
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          );
                        }}
                      />
                    </div>

                    {/* Activity Master guidance for a quantity-only mode
                        (NUMERIC / NUMERIC_DAILY). Task modes render their note
                        inside the Task benchmark card instead, so the same
                        remark is never printed twice on one row.

                        Read-only: this is guidance TO the employee, deliberately
                        kept distinct from their own Remarks input below. A
                        remark that merely restates the configured target or
                        period is dropped - see isDuplicateRemark. */}
                    {(() => {
                      const subId = watchedTasks?.[index]?.sub_activity_id;
                      const sub = subId ? subActivityById.get(subId) : undefined;
                      if (!sub || isTaskBenchmark(sub.benchmark_type)) return null;
                      const remarks = sub.benchmark_remarks?.trim();
                      if (!remarks) return null;
                      const unit = isQuantityBenchmark(sub.benchmark_type)
                        ? sub.relevant_count_field
                        : null;
                      if (
                        isDuplicateRemark(
                          remarks,
                          sub.benchmark_period_days,
                          sub.benchmark_value,
                          unit,
                        )
                      ) {
                        return null;
                      }
                      return (
                        // whitespace-pre-line: multi-line remarks keep their line
                        // breaks and stored wording verbatim.
                        <p className="whitespace-pre-line text-xs text-muted-foreground">
                          <span className="font-medium text-foreground">Note:</span>{" "}
                          {remarks}
                        </p>
                      );
                    })()}

                    {/* Row B2: quantity counts. The sub-activity's configured unit
                        is shown prominently with its read-only target; the other
                        five stay collapsed so six equal inputs are never presented.
                        A status-only task has no quantity of its own, so nothing is
                        promoted for it. */}
                    {(() => {
                      const subId = watchedTasks?.[index]?.sub_activity_id;
                      const sub = subId ? subActivityById.get(subId) : undefined;
                      const row = watchedTasks?.[index];
                      // The configured unit — the ONLY field the benchmark reads.
                      const unit = isQuantityBenchmark(sub?.benchmark_type)
                        ? sub!.relevant_count_field
                        : null;
                      const targetName = unit ? countFieldName(unit) : null;
                      // A half day halves every benchmark target (100 -> 50),
                      // matching the deficit/productivity the backend freezes
                      // at submit time.
                      const isHalfDay = dayStatus === "half_day";
                      const targetValue =
                        sub?.benchmark_value != null
                          ? isHalfDay
                            ? sub.benchmark_value / 2
                            : sub.benchmark_value
                          : null;

                      const others = ALL_COUNT_FIELDS.filter((n) => n !== targetName);
                      // Never hide a stored value: if any collapsed unit already
                      // carries a number (a legacy row, or an edit after the
                      // master's unit changed), the panel opens so it stays
                      // visible and editable rather than silently invisible.
                      const othersHaveValues = others.some(
                        (n) => Number(row?.[n] ?? 0) > 0,
                      );

                      const renderCount = (
                        name: CountFieldName,
                        label: string,
                        prominent: boolean,
                      ) => (
                        <FormField
                          key={name}
                          control={form.control}
                          name={`tasks.${index}.${name}`}
                          render={({ field: f }) => (
                            <FormItem>
                              <FormLabel
                                className={
                                  prominent
                                    ? "block text-sm font-semibold leading-none text-foreground"
                                    : "block text-xs leading-none text-muted-foreground"
                                }
                              >
                                {label}
                                {prominent && <span className="text-destructive"> *</span>}
                              </FormLabel>
                              <FormControl>
                                {/* CountInput (text + numeric keypad), NOT a native
                                    number input: scrolling toward Save must never
                                    change a focused count (the 81→83→81 bug). */}
                                <CountInput
                                  placeholder="0"
                                  className={prominent ? "border-primary" : undefined}
                                  {...f}
                                />
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )}
                        />
                      );

                      return (
                        <div className="space-y-3">
                          {targetName && unit && (
                            <div className="rounded-md border border-primary/40 p-3">
                              <div className="mb-2 flex flex-wrap items-baseline gap-x-2">
                                <span className="text-sm font-medium text-foreground">
                                  {COUNT_FIELD_LABEL[unit]}
                                </span>
                              </div>
                              <div className="sm:max-w-xs">
                                {/* The target IS the input's label: the employee
                                    reads what is expected of them on the same line
                                    they type into. It comes from Activity Master
                                    and is never re-entered here. */}
                                {renderCount(
                                  targetName,
                                  `Target: ${formatInt(targetValue)} ${COUNT_FIELD_LABEL[
                                    unit
                                  ].toUpperCase()} / ${sub!.benchmark_period_days ?? 1}d`,
                                  true,
                                )}
                              </div>
                            </div>
                          )}
                          <details open={othersHaveValues} className="group">
                            <summary className="cursor-pointer list-none text-xs text-muted-foreground hover:text-foreground">
                              <span className="group-open:hidden">
                                + Other counts (optional)
                              </span>
                              <span className="hidden group-open:inline">
                                - Other counts (optional)
                              </span>
                            </summary>
                            <div className="mt-3 grid gap-4 sm:grid-cols-3">
                              {others.map((name) =>
                                renderCount(
                                  name,
                                  COUNT_FIELD_LABEL[
                                    (Object.keys(COUNT_FIELD_KEY) as RelevantCountField[]).find(
                                      (u) => COUNT_FIELD_KEY[u] === name,
                                    )!
                                  ],
                                  false,
                                ),
                              )}
                            </div>
                          </details>
                        </div>
                      );
                    })()}

                    {/* Row C: every TASK mode (TASK_BASED / TASK_STATUS_ONLY /
                        TASK_WITH_QUANTITY) — one compact benchmark + completion
                        card. The headline is generated from the structured
                        fields (benchmark_value / benchmark_period_days /
                        relevant_count_field / due_date), so the rule is stated
                        once and Activity Master remarks only appear when they add
                        something the structured fields do not already say.

                        No status dropdown, no manual date entry:
                        started_date/due_date/completed_date are all system-managed
                        (see schemas.ts).

                        Quantity-only modes (NUMERIC / NUMERIC_DAILY) get NO card:
                        they are pure daily production with nothing to complete. */}
                    {(() => {
                      const subId = watchedTasks?.[index]?.sub_activity_id;
                      const sub = subId ? subActivityById.get(subId) : undefined;
                      if (!isTaskBenchmark(sub?.benchmark_type)) return null;

                      const row = watchedTasks?.[index];
                      // Prefer the server-computed due_date (existing row);
                      // for a brand-new row not yet saved, preview it
                      // client-side from the report date + allocated duration.
                      // due_date = started_on + (target_days - 1): a 1-day task
                      // is due the day it starts, a 2-day task the next day, etc.
                      // target_days is clamped to >= 1 (a 0/blank benchmark period
                      // must never push the due date before the start date).
                      const periodDays = Math.max(1, sub!.benchmark_period_days ?? 1);
                      const previewDue = row?.due_date
                        ? row.due_date
                        : reportDate
                          ? addDays(reportDate, periodDays - 1)
                          : null;
                      const dueLabel = formatDueDate(previewDue);

                      const unit = isQuantityBenchmark(sub!.benchmark_type)
                        ? sub!.relevant_count_field
                        : null;
                      // Same half-day rule as the quantity input above: a half
                      // day halves the target the employee is measured against.
                      const target =
                        sub!.benchmark_value != null
                          ? dayStatus === "half_day"
                            ? sub!.benchmark_value / 2
                            : sub!.benchmark_value
                          : null;

                      const remarks = sub!.benchmark_remarks?.trim();
                      const showNote =
                        remarks &&
                        !isDuplicateRemark(
                          remarks,
                          sub!.benchmark_period_days,
                          sub!.benchmark_value,
                          unit,
                        );

                      return (
                        <div className="rounded-md border border-border p-3">
                          <p className="text-xs font-medium text-foreground">
                            Task benchmark
                          </p>
                          <p className="mt-1 text-xs text-muted-foreground">
                            {/* A quantity task states its target on the input's
                                own label, which is authoritative - the card adds
                                only the deadline, never a second copy of the
                                target. A status-only task has no quantity input,
                                so it states the whole rule here. */}
                            {unit && target != null && dueLabel ? (
                              <>Due: {dueLabel}</>
                            ) : (
                              <>
                                Complete within {periodDays}{" "}
                                {periodDays === 1 ? "day" : "days"}.
                                {dueLabel ? ` Due: ${dueLabel}` : ""}
                              </>
                            )}
                          </p>
                          {showNote && (
                            // whitespace-pre-line: multi-line remarks keep their
                            // line breaks and stored wording verbatim.
                            <p className="mt-1 whitespace-pre-line text-xs text-muted-foreground">
                              <span className="font-medium text-foreground">Note:</span>{" "}
                              {remarks}
                            </p>
                          )}
                          <FormField
                            control={form.control}
                            name={`tasks.${index}.is_completed`}
                            render={({ field: f }) => (
                              <FormItem className="mt-3">
                                {/* Stated once, above the box - the checked state
                                    replaces it rather than adding a second copy. */}
                                {!f.value && (
                                  <p className="mb-2 text-xs text-muted-foreground">
                                    Leave unchecked if unfinished; the task will
                                    continue in your next report.
                                  </p>
                                )}
                                <label className="flex items-center gap-2 text-sm">
                                  <FormControl>
                                    <Checkbox
                                      checked={f.value}
                                      onChange={(e) => f.onChange(e.target.checked)}
                                    />
                                  </FormControl>
                                  <span className="font-medium text-foreground">
                                    Mark task fully completed
                                  </span>
                                </label>
                                {f.value && (
                                  <p className="mt-2 text-xs font-medium text-foreground">
                                    Task completed - it will no longer carry forward.
                                  </p>
                                )}
                                <FormMessage />
                              </FormItem>
                            )}
                          />
                        </div>
                      );
                    })()}
                  </div>
                );
              })}

              {tasksError && (
                <p className="text-xs font-medium text-destructive">{tasksError}</p>
              )}

              {/* Second-activity flow. The first activity is added freely with
                  "Add Activity" (unchanged). A second activity is filled the
                  same way; routine ones (meeting / training - see
                  NO_APPROVAL_ACTIVITIES) save straight onto the report, while
                  any other activity must be approved by the PM: the draft is
                  sent as a request and shown as Pending until decided. */}
              {pendingRequest ? (
                <RequestStatusCard
                  request={pendingRequest}
                  activityNo={fields.length + 1}
                />
              ) : rejectedRequest ? (
                <RequestStatusCard
                  request={rejectedRequest}
                  activityNo={fields.length + 1}
                  onDismiss={() => void dismissRejectedRequest()}
                  dismissing={deleteActivityRequest.isPending}
                />
              ) : secondDraft ? (
                secondActivityNeedsApproval(
                  watchedTasks?.[0],
                  watchedTasks?.[fields.length - 1],
                ) ? (
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
                  // No approval needed — either this activity or the day's first
                  // activity is a routine one; it saves with the report.
                  <p className="rounded-lg border border-dashed border-border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
                    This activity does not need PM approval - it will be saved with
                    the report when you save.
                  </p>
                )
              ) : fields.length >= 1 ? (
                <Button type="button" variant="secondary" onClick={addSecondActivityDraft}>
                  <Plus className="h-4 w-4" />
                  Add Activity
                </Button>
              ) : null}
                </>
              )}
            </div>

            <Separator />

            {/* ── Day Remarks — one remark for the whole day (not per activity) ── */}
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
      </CardContent>
    </Card>
  );
}
