"use client";

import { EmptyState } from "@/components/feedback/empty-state";
import { TableSkeleton } from "@/components/feedback/table-skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

import { useContinuationRequestList } from "../hooks";
import { ContinuationStatusBadge } from "./continuation-status-badge";

const LIMIT = 50;

export function AllContinuationRequestsList() {
  const query = useContinuationRequestList({ status: "", limit: LIMIT, offset: 0 });
  const items = query.data?.items ?? [];

  if (query.isLoading) return <TableSkeleton rows={5} cols={7} />;
  if (items.length === 0) {
    return (
      <EmptyState
        title="No continuation requests"
        description="No requests have been filed yet."
      />
    );
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Employee</TableHead>
          <TableHead>Project</TableHead>
          <TableHead>Activity</TableHead>
          <TableHead>Requested Date</TableHead>
          <TableHead>Decision Date</TableHead>
          <TableHead>Reviewer</TableHead>
          <TableHead>Status</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {items.map((req) => (
          <TableRow key={req.id}>
            <TableCell className="font-medium">{req.employee_name}</TableCell>
            <TableCell>{req.project_code || req.project_name}</TableCell>
            <TableCell>
              {req.activity_name
                ? `${req.activity_name} / ${req.sub_activity_name}`
                : req.sub_activity_name}
            </TableCell>
            <TableCell className="tabular">{req.requested_at.slice(0, 10)}</TableCell>
            <TableCell className="tabular">
              {req.decided_at ? req.decided_at.slice(0, 10) : "-"}
            </TableCell>
            <TableCell>{req.reviewer_name ?? "-"}</TableCell>
            <TableCell>
              <ContinuationStatusBadge status={req.status} />
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
