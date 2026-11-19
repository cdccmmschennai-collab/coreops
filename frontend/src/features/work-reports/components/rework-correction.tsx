"use client";

import * as React from "react";
import { PencilLine } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Combobox } from "@/components/ui/combobox";
import { CountInput } from "@/components/ui/count-input";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { AppError } from "@/lib/api-client";
import { useSubActivityOptions } from "@/features/activity-master/hooks";
import {
  COUNT_FIELDS,
  COUNT_FIELD_KEY,
  COUNT_FIELD_LABEL,
  isQuantityBenchmark,
  isTaskBenchmark,
  type RelevantCountField,
} from "@/features/activity-master/types";
import { useCorrectReworkRequest, useReworkRequest } from "@/features/rework-approvals/hooks";

import {
  PM_APPROVAL_REQUIRED_LABEL,
  buildCorrectionBody,
  correctionBenchmark,
} from "../rework-approval";
import type { WorkReportTask } from "../types";

/**
 * Shown on a REJECTED rework row, to its author, on a submitted report:
 * the PM's reason plus "Correct & Resubmit". Only this row changes - the
 * report stays submitted and every other activity is left exactly as it is.
 */
export function RejectedReworkPanel({ task }: { task: WorkReportTask }) {
  const requestId = task.rework_request_id ?? "";
  const request = useReworkRequest(requestId);
  const [open, setOpen] = React.useState(false);

  return (
    <div className="mt-2 space-y-2 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2">
      <p className="text-xs">
        <span className="font-medium text-destructive">Rejected by your PM</span>
        {request.data?.reviewer_name ? ` (${request.data.reviewer_name})` : ""}
        {request.data?.review_remarks ? `: ${request.data.review_remarks}` : ""}
      </p>
      <p className="text-xs text-muted-foreground">
        Correct this activity and resubmit it. Your other activities on this report are unchanged.
      </p>
      <Button size="sm" variant="secondary" onClick={() => setOpen(true)}>
        <PencilLine className="h-3.5 w-3.5" />
        Correct &amp; Resubmit
      </Button>
      {open && (
        <CorrectionDialog task={task} requestId={requestId} onClose={() => setOpen(false)} />
      )}
    </div>
  );
}

function CorrectionDialog({
  task,
  requestId,
  onClose,
}: {
  task: WorkReportTask;
  requestId: string;
  onClose: () => void;
}) {
  const { items: subs, byId } = useSubActivityOptions();
  const correct = useCorrectReworkRequest(requestId);

  const initialSub = task.sub_activity_id ?? "";
  const [activityId, setActivityId] = React.useState(byId.get(initialSub)?.activity_id ?? "");
  const [subId, setSubId] = React.useState(initialSub);
  const [description, setDescription] = React.useState(task.description ?? "");
  const [count, setCount] = React.useState("");
  const [lumpsumUnit, setLumpsumUnit] = React.useState<RelevantCountField | "">("");

  // The dropdown data may arrive after mount; settle the parent once it does.
  React.useEffect(() => {
    if (!activityId && initialSub && byId.get(initialSub)) {
      setActivityId(byId.get(initialSub)!.activity_id);
    }
  }, [activityId, initialSub, byId]);

  const activityOptions = React.useMemo(() => {
    const seen = new Map<string, string>();
    for (const s of subs) if (!seen.has(s.activity_id)) seen.set(s.activity_id, s.activity_name);
    return [...seen].map(([value, label]) => ({ value, label }));
  }, [subs]);
  const subOptions = React.useMemo(
    () =>
      subs
        .filter((s) => s.activity_id === activityId)
        .map((s) => ({
          value: s.id,
          label: s.name,
          sublabel: s.requires_pm_approval ? PM_APPROVAL_REQUIRED_LABEL : undefined,
        })),
    [subs, activityId],
  );

  const sub = subId ? byId.get(subId) : undefined;
  const quantityUnit =
    sub && isQuantityBenchmark(sub.benchmark_type) ? sub.relevant_count_field : null;
  const isLumpsum = !!sub && isTaskBenchmark(sub.benchmark_type) && !sub.relevant_count_field;
  // Target under the count (quantity), the completion tick (task modes), or
  // both (TASK_WITH_QUANTITY) - scaled to this row's day part.
  const benchmark = correctionBenchmark(sub, task.day_part);
  const [isCompleted, setIsCompleted] = React.useState(false);

  // Reset the count whenever the unit it belongs to changes.
  React.useEffect(() => {
    if (quantityUnit) {
      const key = COUNT_FIELD_KEY[quantityUnit] as keyof WorkReportTask;
      setCount(subId === initialSub ? String(task[key] ?? "") : "");
    } else {
      setCount("");
    }
    setLumpsumUnit("");
    setIsCompleted(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [subId, quantityUnit]);

  async function submit() {
    if (!subId) {
      toast.error("Choose a sub-activity.");
      return;
    }
    const n = count.trim() === "" ? null : Number(count);
    if (isLumpsum && n && !lumpsumUnit) {
      toast.error("Choose what the count is for.");
      return;
    }
    const body = buildCorrectionBody(
      {
        project_id: task.project_id,
        project_code: task.project_code,
        tags_count: task.tags_count,
        docs_count: task.docs_count,
        bom_count: task.bom_count,
        spares_count: task.spares_count,
        pages_count: task.pages_count,
        records_count: task.records_count,
      },
      {
        subActivityId: subId,
        description,
        countColumn: quantityUnit ? COUNT_FIELD_KEY[quantityUnit] : null,
        count: n,
        lumpsumUnit: isLumpsum ? lumpsumUnit || null : null,
        isCompleted: benchmark.showCompletion && isCompleted,
      },
    );
    try {
      const report = await correct.mutateAsync(body);
      const stillRework = (report.tasks ?? []).some(
        (t) => (t as WorkReportTask).rework_approval_status === "pending",
      );
      toast.success(
        stillRework
          ? "Resubmitted - rework approval requested from your PM"
          : "Activity corrected and submitted",
      );
      onClose();
    } catch (err) {
      toast.error(err instanceof AppError ? err.message : "Could not resubmit the activity.");
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Correct &amp; Resubmit Activity</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <p className="text-xs text-muted-foreground">
            Project: <span className="font-medium text-foreground">{task.project_code ?? "-"}</span>
          </p>
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground">Activity</label>
            <Combobox
              value={activityId}
              onValueChange={(v) => {
                setActivityId(v);
                setSubId("");
              }}
              options={activityOptions}
              placeholder="Select activity..."
              searchPlaceholder="Search activities..."
              emptyMessage="No matching activities."
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground">Sub-Activity</label>
            <Combobox
              value={subId}
              onValueChange={setSubId}
              options={subOptions}
              placeholder={activityId ? "Select sub-activity..." : "Pick an Activity first"}
              searchPlaceholder="Search sub-activities..."
              emptyMessage="No matching sub-activities."
              disabled={!activityId}
            />
            {sub?.requires_pm_approval && (
              <p className="text-xs text-warning">
                This sub-activity needs PM approval - it will go back to your PM for review.
              </p>
            )}
          </div>
          {quantityUnit && (
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">
                {COUNT_FIELD_LABEL[quantityUnit]}
              </label>
              <CountInput value={count} onChange={(e) => setCount(e.target.value)} />
              {benchmark.target !== null && (
                <p className="text-xs text-muted-foreground">
                  Target: <span className="font-medium text-foreground">{benchmark.target}</span>{" "}
                  {COUNT_FIELD_LABEL[quantityUnit]}
                  {task.day_part === "first_half" || task.day_part === "second_half"
                    ? " (half day)"
                    : ""}
                </p>
              )}
            </div>
          )}
          {isLumpsum && (
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">Count (optional)</label>
                <CountInput value={count} onChange={(e) => setCount(e.target.value)} />
              </div>
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">Unit</label>
                <Select
                  value={lumpsumUnit}
                  onValueChange={(v) => setLumpsumUnit(v as RelevantCountField)}
                >
                  <SelectTrigger aria-label="Count unit">
                    <SelectValue placeholder="Select unit" />
                  </SelectTrigger>
                  <SelectContent>
                    {COUNT_FIELDS.map((u) => (
                      <SelectItem key={u} value={u}>
                        {COUNT_FIELD_LABEL[u]}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          )}
          {benchmark.showCompletion && (
            <div className="space-y-1 rounded-md border border-border p-3">
              <p className="text-xs font-medium text-foreground">Task benchmark</p>
              {benchmark.periodDays !== null && (
                <p className="text-xs text-muted-foreground">
                  Complete within {benchmark.periodDays}{" "}
                  {benchmark.periodDays === 1 ? "day" : "days"}.
                </p>
              )}
              <label className="mt-2 flex items-center gap-2 text-sm">
                <Checkbox
                  checked={isCompleted}
                  onChange={(e) => setIsCompleted(e.target.checked)}
                />
                <span className="font-medium text-foreground">Mark task fully completed</span>
              </label>
              <p className="text-xs text-muted-foreground">
                {isCompleted
                  ? "Task completed - it will no longer carry forward."
                  : "Leave unchecked if unfinished; the task will continue in your next report."}
              </p>
            </div>
          )}
          <div className="space-y-1">
            <label htmlFor="rework-correction-remarks" className="text-xs text-muted-foreground">
              Remarks
            </label>
            <Textarea
              id="rework-correction-remarks"
              rows={4}
              maxLength={2000}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Explain the work for your PM..."
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={correct.isPending}>
            Cancel
          </Button>
          <Button onClick={() => void submit()} loading={correct.isPending}>
            Resubmit
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
