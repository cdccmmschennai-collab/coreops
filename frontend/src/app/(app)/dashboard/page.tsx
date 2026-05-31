"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PageHeader } from "@/components/shell/page-header";
import { useAuth } from "@/features/auth/auth-provider";

function greeting(): string {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}

export default function DashboardPage() {
  const { user } = useAuth();
  const name = user?.email.split("@")[0] ?? "there";

  return (
    <>
      <PageHeader
        title={`${greeting()}, ${name}`}
        subtitle="Workforce Management System"
      />
      <Card>
        <CardHeader>
          <CardTitle>You are signed in</CardTitle>
        </CardHeader>
        <CardContent className="space-y-1 text-sm text-muted-foreground">
          <p>
            Email: <span className="text-foreground">{user?.email}</span>
          </p>
          <p>
            Role:{" "}
            <span className="capitalize text-foreground">{user?.role}</span>
          </p>
          <p className="pt-2">
            This is a placeholder home. The full dashboard (KPIs, recent reports,
            charts) is built in a later phase (F2). Employees, Projects,
            Attendance, and Reports are not built yet.
          </p>
        </CardContent>
      </Card>
    </>
  );
}
