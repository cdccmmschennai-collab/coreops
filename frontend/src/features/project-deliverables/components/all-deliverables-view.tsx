"use client";

import Link from "next/link";

import { ErrorState } from "@/components/feedback/error-state";
import { PageHeader } from "@/components/shell/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

import { useAllDeliverables } from "../hooks";
import { DeliverableStatusBadge } from "./status-badge";

export function AllDeliverablesView() {
  const query = useAllDeliverables();

  return (
    <>
      <Link href="/projects" className="text-sm text-primary hover:underline">
        ← Back
      </Link>
      <PageHeader className="mt-2" title="Deliverables" />

      <Card>
        <CardContent className="p-0">
          {query.isLoading ? (
            <div className="space-y-2 p-4">
              <Skeleton className="h-8 w-full" />
              <Skeleton className="h-8 w-5/6" />
              <Skeleton className="h-8 w-3/4" />
            </div>
          ) : query.isError ? (
            <ErrorState
              title="Could not load deliverables"
              message="Please try again."
              onRetry={() => void query.refetch()}
            />
          ) : !query.data?.length ? (
            <p className="p-4 text-sm text-muted-foreground">No deliverables found.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Project</TableHead>
                  <TableHead>Name</TableHead>
                  <TableHead>Owner</TableHead>
                  <TableHead>Target Date</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {query.data.map((d) => (
                  <TableRow key={d.id}>
                    <TableCell className="text-sm">
                      <Link
                        href={`/projects/${d.project_id}`}
                        className="text-primary hover:underline font-mono"
                      >
                        {d.project_code ?? d.project_id}
                      </Link>
                      {d.project_name && (
                        <div className="text-xs text-muted-foreground mt-0.5">
                          {d.project_name}
                        </div>
                      )}
                    </TableCell>
                    <TableCell className="font-medium">
                      <div>{d.name}</div>
                      {d.description && (
                        <div className="text-xs text-muted-foreground mt-0.5 line-clamp-1">
                          {d.description}
                        </div>
                      )}
                    </TableCell>
                    <TableCell className="text-sm">
                      {d.owner_name ?? <span className="text-muted-foreground">—</span>}
                    </TableCell>
                    <TableCell className="text-sm">
                      {d.target_date ?? <span className="text-muted-foreground">—</span>}
                    </TableCell>
                    <TableCell>
                      <DeliverableStatusBadge status={d.status} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </>
  );
}
