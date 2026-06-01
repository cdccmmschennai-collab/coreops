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

const EVENTS = [
  { time: "4:32 PM",           actor: "Priya Ramanujan",  action: "submitted",     object: "Work report · Jun 01",          meta: "from 10.42.18.205" },
  { time: "3:14 PM",           actor: "Marco Velez",      action: "approved",      object: "Work report · Lin Chen · May 29", meta: "manager workflow" },
  { time: "2:08 PM",           actor: "system",           action: "auto-locked",   object: "Reports for May 31",              meta: "scheduled · 00:00 IST" },
  { time: "1:46 PM",           actor: "Tomás Ribeiro",    action: "invited",       object: "sam@example.com · Viewer",        meta: "invite expires 7 days" },
  { time: "11:08 AM",          actor: "Marco Velez",      action: "modified role", object: "Tomás Ribeiro → Manager",         meta: "previously Employee" },
  { time: "Yesterday 4:22 PM", actor: "system",           action: "exported",      object: "Monthly attendance · May",        meta: "PDF · 47 employees" },
  { time: "Yesterday 9:01 AM", actor: "Priya Ramanujan",  action: "created",       object: "Project Apollo",                  meta: "duplicated from sprint 13" },
  { time: "May 22, 5:14 PM",   actor: "Lin Chen",         action: "requested",     object: "Attendance correction · May 21",  meta: null },
];

export function AuditLogPreview() {
  return (
    <div>
      <PreviewBanner>the Audit log module is not built yet. Events shown are sample data.</PreviewBanner>
      <Card className="overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Time</TableHead>
              <TableHead>Actor</TableHead>
              <TableHead>Action</TableHead>
              <TableHead>Object</TableHead>
              <TableHead>Context</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {EVENTS.map((e, i) => (
              <TableRow key={i}>
                <TableCell className="tabular text-xs text-muted-foreground">{e.time}</TableCell>
                <TableCell className="text-sm font-medium">{e.actor}</TableCell>
                <TableCell className="text-sm text-muted-foreground">{e.action}</TableCell>
                <TableCell className="text-sm text-primary">{e.object}</TableCell>
                <TableCell className="tabular text-xs text-muted-foreground">{e.meta ?? "—"}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}
