"use client";

import * as React from "react";
import { ChevronLeft, Plus, Trash2 } from "lucide-react";
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
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { AppError } from "@/lib/api-client";

import {
  useDeleteSubmission,
  useSubmissions,
  useUpdateSubmissionStatus,
} from "../hooks";
import type { Submission, SubmissionStatus } from "../types";
import { SUBMISSION_STATUS_LABEL } from "../types";
import { SubmissionForm } from "./submission-form";
import { SubmissionStatusBadge } from "./submission-status-badge";

// ── status action config ──────────────────────────────────────────────────────

type StatusAction = {
  label: string;
  next: SubmissionStatus;
  needsNote: boolean;
};

const STATUS_ACTIONS: Partial<Record<SubmissionStatus, StatusAction[]>> = {
  draft: [{ label: "Mark as Submitted", next: "submitted", needsNote: false }],
  submitted: [
    { label: "Approve", next: "approved", needsNote: false },
    { label: "Reject", next: "rejected", needsNote: true },
  ],
  rejected: [{ label: "Re-open as Draft", next: "draft", needsNote: false }],
};

// ── status update dialog ──────────────────────────────────────────────────────

function StatusDialog({
  projectId,
  submission,
  action,
  open,
  onOpenChange,
}: {
  projectId: string;
  submission: Submission;
  action: StatusAction;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const mutation = useUpdateSubmissionStatus(projectId, submission.id);
  const [note, setNote] = React.useState("");

  React.useEffect(() => {
    if (open) setNote("");
  }, [open]);

  async function handleConfirm() {
    try {
      await mutation.mutateAsync({
        status: action.next,
        review_note: note.trim() || null,
      });
      toast.success(`Submission marked as ${SUBMISSION_STATUS_LABEL[action.next]}`);
      onOpenChange(false);
    } catch (err) {
      toast.error(err instanceof AppError ? err.message : "Something went wrong");
    }
  }

  return (
    <AlertDialog open={open} onOpenChange={mutation.isPending ? undefined : onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{action.label}</AlertDialogTitle>
          <AlertDialogDescription>
            This will change the submission status to{" "}
            <strong>{SUBMISSION_STATUS_LABEL[action.next]}</strong>.
          </AlertDialogDescription>
        </AlertDialogHeader>

        {action.needsNote && (
          <div className="mt-3 space-y-1.5">
            <Label htmlFor="review-note">
              Rejection note{" "}
              <span className="font-normal text-muted-foreground">(optional)</span>
            </Label>
            <Textarea
              id="review-note"
              rows={3}
              placeholder="Reason for rejection…"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              disabled={mutation.isPending}
            />
          </div>
        )}

        <AlertDialogFooter className="mt-4">
          <AlertDialogCancel disabled={mutation.isPending}>Cancel</AlertDialogCancel>
          <Button onClick={handleConfirm} loading={mutation.isPending}>
            Confirm
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

// ── detail view ───────────────────────────────────────────────────────────────

function SubmissionDetail({
  projectId,
  submission,
  canManage,
  onBack,
}: {
  projectId: string;
  submission: Submission;
  canManage: boolean;
  onBack: () => void;
}) {
  const [editing, setEditing] = React.useState(false);
  const [statusAction, setStatusAction] = React.useState<StatusAction | null>(null);
  const [confirmDelete, setConfirmDelete] = React.useState(false);
  const deleteMut = useDeleteSubmission(projectId);

  const actions = STATUS_ACTIONS[submission.status as SubmissionStatus] ?? [];
  const isDraft = submission.status === "draft";

  if (editing) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Edit Submission</CardTitle>
        </CardHeader>
        <CardContent>
          <SubmissionForm
            projectId={projectId}
            existing={submission}
            onDone={() => setEditing(false)}
            onCancel={() => setEditing(false)}
          />
        </CardContent>
      </Card>
    );
  }

  return (
    <>
      <div className="mb-4 flex items-center justify-between gap-3">
        <button
          type="button"
          onClick={onBack}
          className="flex items-center gap-1 text-sm text-primary hover:underline"
        >
          <ChevronLeft className="h-4 w-4" />
          All submissions
        </button>
        {canManage && (
          <div className="flex gap-2">
            {isDraft && (
              <>
                <Button variant="secondary" size="sm" onClick={() => setEditing(true)}>
                  Edit
                </Button>
                <Button
                  variant="danger"
                  size="sm"
                  onClick={() => setConfirmDelete(true)}
                >
                  <Trash2 className="h-4 w-4" />
                  Delete
                </Button>
              </>
            )}
            {actions.map((a) => (
              <Button key={a.next} size="sm" onClick={() => setStatusAction(a)}>
                {a.label}
              </Button>
            ))}
          </div>
        )}
      </div>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>Submission</CardTitle>
          <SubmissionStatusBadge status={submission.status as SubmissionStatus} />
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-3 text-sm">
            <div>
              <div className="text-muted-foreground">Submission date</div>
              <div className="font-medium">{submission.submission_date}</div>
            </div>
            <div>
              <div className="text-muted-foreground">Period</div>
              <div className="font-medium">
                {submission.period_start} – {submission.period_end}
              </div>
            </div>
            <div>
              <div className="text-muted-foreground">Submitted by</div>
              <div className="font-medium">{submission.submitted_by_name}</div>
            </div>
          </div>

          {submission.notes && (
            <div className="text-sm">
              <div className="mb-1 text-muted-foreground">Notes</div>
              <p className="whitespace-pre-wrap">{submission.notes}</p>
            </div>
          )}

          {submission.reviewed_at && (
            <div className="rounded-md border border-border bg-muted/30 p-3 text-sm">
              <div className="font-medium">Review — {SUBMISSION_STATUS_LABEL[submission.status as SubmissionStatus]}</div>
              {submission.review_note && (
                <p className="mt-1 text-muted-foreground">{submission.review_note}</p>
              )}
              <p className="mt-1 text-xs text-muted-foreground">
                {submission.reviewed_by_name} · {new Date(submission.reviewed_at).toLocaleDateString()}
              </p>
            </div>
          )}

          <div>
            <div className="mb-2 text-sm font-medium">Items</div>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Activity</TableHead>
                  <TableHead className="text-right">Quantity</TableHead>
                  <TableHead>Unit</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {submission.items.map((item) => (
                  <TableRow key={item.id}>
                    <TableCell>{item.activity_label}</TableCell>
                    <TableCell className="text-right tabular">{item.quantity.toLocaleString()}</TableCell>
                    <TableCell className="text-muted-foreground">{item.unit}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      {statusAction && (
        <StatusDialog
          projectId={projectId}
          submission={submission}
          action={statusAction}
          open={!!statusAction}
          onOpenChange={(open) => { if (!open) setStatusAction(null); }}
        />
      )}

      <AlertDialog open={confirmDelete} onOpenChange={setConfirmDelete}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete submission?</AlertDialogTitle>
            <AlertDialogDescription>
              This draft submission will be permanently deleted.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={async () => {
                try {
                  await deleteMut.mutateAsync(submission.id);
                  toast.success("Submission deleted");
                  onBack();
                } catch {
                  toast.error("Could not delete submission");
                }
              }}
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}

// ── list view ─────────────────────────────────────────────────────────────────

export function SubmissionsTab({
  projectId,
  canManage,
}: {
  projectId: string;
  canManage: boolean;
}) {
  const query = useSubmissions(projectId);
  const [selected, setSelected] = React.useState<Submission | null>(null);
  const [creating, setCreating] = React.useState(false);

  const submissions = query.data ?? [];

  if (selected) {
    const live = submissions.find((s) => s.id === selected.id) ?? selected;
    return (
      <SubmissionDetail
        projectId={projectId}
        submission={live}
        canManage={canManage}
        onBack={() => setSelected(null)}
      />
    );
  }

  if (creating) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>New Submission</CardTitle>
        </CardHeader>
        <CardContent>
          <SubmissionForm
            projectId={projectId}
            onDone={() => setCreating(false)}
            onCancel={() => setCreating(false)}
          />
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      {canManage && (
        <div className="flex justify-end">
          <Button onClick={() => setCreating(true)}>
            <Plus className="h-4 w-4" />
            New submission
          </Button>
        </div>
      )}

      <Card>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Submission date</TableHead>
              <TableHead>Period</TableHead>
              <TableHead>Items</TableHead>
              <TableHead>Status</TableHead>
            </TableRow>
          </TableHeader>

          {query.isLoading && (
            <TableBody>
              {[1, 2, 3].map((n) => (
                <TableRow key={n}>
                  {[1, 2, 3, 4].map((c) => (
                    <TableCell key={c}><Skeleton className="h-4 w-full" /></TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          )}

          {!query.isLoading && (
            <TableBody>
              {submissions.length === 0 && (
                <TableRow>
                  <TableCell colSpan={4} className="py-8 text-center text-muted-foreground text-sm">
                    No submissions yet.{canManage ? " Create the first one above." : ""}
                  </TableCell>
                </TableRow>
              )}
              {submissions.map((s) => (
                <TableRow
                  key={s.id}
                  className="cursor-pointer"
                  onClick={() => setSelected(s)}
                >
                  <TableCell className="font-medium">{s.submission_date}</TableCell>
                  <TableCell className="text-muted-foreground">
                    {s.period_start} – {s.period_end}
                  </TableCell>
                  <TableCell className="tabular text-muted-foreground">
                    {s.items.length}
                  </TableCell>
                  <TableCell>
                    <SubmissionStatusBadge status={s.status as SubmissionStatus} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          )}
        </Table>
      </Card>
    </div>
  );
}
