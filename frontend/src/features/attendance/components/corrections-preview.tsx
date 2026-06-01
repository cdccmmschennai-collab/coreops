import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

import { PreviewBanner } from "./preview-banner";

const ROWS: {
  date: string;
  reason: string;
  submitted: string;
  status: string;
  variant: "warning" | "success";
}[] = [
  { date: "May 21", reason: "Forgot to punch out — left at 19:30", submitted: "2 days ago", status: "pending review", variant: "warning" },
  { date: "May 14", reason: "Holiday marked as absent — Buddha Purnima", submitted: "1 week ago", status: "approved", variant: "success" },
  { date: "May 06", reason: "Punch in counted twice (09:00 + 09:04)", submitted: "1 week ago", status: "approved", variant: "success" },
];

export function CorrectionsPreview() {
  return (
    <div>
      <PreviewBanner>
        the attendance corrections workflow is not built yet. Rows shown are sample data.
      </PreviewBanner>
      <Card className="overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Date</TableHead>
              <TableHead>Reason</TableHead>
              <TableHead>Submitted</TableHead>
              <TableHead>Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {ROWS.map((r, i) => (
              <TableRow key={i}>
                <TableCell className="font-medium">{r.date}</TableCell>
                <TableCell className="text-muted-foreground">{r.reason}</TableCell>
                <TableCell className="tabular text-xs text-muted-foreground">{r.submitted}</TableCell>
                <TableCell>
                  <Badge variant={r.variant}>{r.status}</Badge>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}
