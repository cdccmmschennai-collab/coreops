import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { PreviewBanner } from "@/features/attendance/components/preview-banner";

const ROWS = [
  { name: "Ana Núñez",      type: "CL", from: "May 28", to: "May 28", days: 1, reason: "Family event",            applied: "2 days ago" },
  { name: "Lin Chen",       type: "SL", from: "May 27", to: "May 28", days: 2, reason: "Doctor visit + recovery", applied: "1 day ago" },
  { name: "Jordan Kim",     type: "EL", from: "Jun 02", to: "Jun 06", days: 5, reason: "Annual trip",             applied: "3 hours ago" },
  { name: "Hassan Al-Awar", type: "CO", from: "May 30", to: "May 30", days: 1, reason: "Comp off for May 1 work", applied: "Yesterday" },
];

export function LeaveApprovalsPreview() {
  return (
    <div>
      <PreviewBanner>the Leave module is not built yet. Requests shown are sample data.</PreviewBanner>
      <Card className="overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Employee</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Dates</TableHead>
              <TableHead>Days</TableHead>
              <TableHead>Reason</TableHead>
              <TableHead>Applied</TableHead>
              <TableHead>Action</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {ROWS.map((r, i) => (
              <TableRow key={i}>
                <TableCell className="font-medium">{r.name}</TableCell>
                <TableCell>
                  <Badge variant="info">{r.type}</Badge>
                </TableCell>
                <TableCell className="tabular text-sm">
                  <div>{r.from}</div>
                  <div className="text-xs text-muted-foreground">→ {r.to}</div>
                </TableCell>
                <TableCell className="tabular">{r.days}d</TableCell>
                <TableCell className="max-w-[200px] truncate text-muted-foreground">{r.reason}</TableCell>
                <TableCell className="tabular text-xs text-muted-foreground">{r.applied}</TableCell>
                <TableCell>
                  <div className="flex gap-1.5">
                    <Button size="sm" disabled>Approve</Button>
                    <Button size="sm" variant="ghost" disabled>Deny</Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}
