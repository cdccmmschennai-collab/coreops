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
  { name: "Lin Chen",  date: "May 21", reason: "Forgot to punch out - left at 19:30",               applied: "2 days ago" },
  { name: "Riya Shah", date: "May 19", reason: "Punch system was down between 09:00 and 09:20",     applied: "Yesterday" },
];

export function AdminCorrectionsPreview() {
  return (
    <div>
      <PreviewBanner>the Attendance Corrections workflow is not built yet. Requests shown are sample data.</PreviewBanner>
      <Card className="overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Employee</TableHead>
              <TableHead>Date</TableHead>
              <TableHead>Reason</TableHead>
              <TableHead>Applied</TableHead>
              <TableHead>Action</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {ROWS.map((r, i) => (
              <TableRow key={i}>
                <TableCell className="font-medium">{r.name}</TableCell>
                <TableCell className="tabular">{r.date}</TableCell>
                <TableCell className="text-muted-foreground">{r.reason}</TableCell>
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
