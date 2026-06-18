import { Card } from "@/components/ui/card";

const ROLES = [
  {
    name: "Project Manager",
    desc: "Full access - manage employees, projects, roles, and master data, and review work reports, attendance, and leave.",
  },
  {
    name: "Employee",
    desc: "Submit and edit own work reports, view own attendance, request leave, and access assigned projects.",
  },
] as const;

export function RolesTab() {
  return (
    <Card className="overflow-hidden">
      {ROLES.map((r, i) => (
        <div
          key={r.name}
          className="flex items-center px-5 py-4"
          style={{ borderBottom: i < ROLES.length - 1 ? "1px solid hsl(var(--border))" : undefined }}
        >
          <div className="flex-1">
            <div className="font-medium">{r.name}</div>
            <div className="mt-0.5 text-sm text-muted-foreground">{r.desc}</div>
          </div>
        </div>
      ))}
    </Card>
  );
}
