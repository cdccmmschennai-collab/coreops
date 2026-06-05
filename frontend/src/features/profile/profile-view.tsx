"use client";

import { Briefcase, Mail, Users } from "lucide-react";

import { DetailField, DetailSection } from "@/components/data/detail-section";
import { BackButton } from "@/components/shell/back-button";
import { PageHeader } from "@/components/shell/page-header";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Card, CardContent } from "@/components/ui/card";
import { useAuth } from "@/features/auth/auth-provider";
import { StatusBadge } from "@/features/employees/components/status-badge";
import { nameInitials } from "@/lib/initials";
import { cn } from "@/lib/utils";

/** Format a date-only string (YYYY-MM-DD) without timezone drift. */
function formatJoinDate(value: string | null): string {
  if (!value) return "—";
  const [y, m, d] = value.split("-").map(Number);
  if (!y || !m || !d) return value;
  return new Date(y, m - 1, d).toLocaleDateString([], {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

export function ProfileView() {
  const { employee, user } = useAuth();

  if (!employee) {
    return (
      <>
        <BackButton fallback="/" />
        <PageHeader title="My Profile" subtitle="Your business identity at CoreOps." />
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            No employee profile is linked to your account
            {user?.email ? ` (${user.email})` : ""}. Please contact your project
            manager.
          </CardContent>
        </Card>
      </>
    );
  }

  const heroSubtitle = [employee.employee_code, employee.designation]
    .filter(Boolean)
    .join(" · ");

  return (
    <>
      <BackButton fallback="/" />
      <PageHeader
        title="My Profile"
        subtitle="Your business identity at CoreOps. This page is read-only."
      />

      <div className="max-w-4xl space-y-4">
        {/* Profile header (hero) */}
        <Card>
          <CardContent
            className={cn(
              "flex flex-col items-center gap-4 p-6 text-center",
              "sm:flex-row sm:items-center sm:text-left",
            )}
          >
            <Avatar className="h-16 w-16">
              <AvatarFallback className="text-lg">
                {nameInitials(employee.full_name)}
              </AvatarFallback>
            </Avatar>
            <div className="min-w-0 flex-1">
              <h2 className="font-serif text-2xl font-semibold tracking-tight text-foreground">
                {employee.full_name}
              </h2>
              {heroSubtitle && (
                <p className="mt-1 text-sm text-muted-foreground">{heroSubtitle}</p>
              )}
            </div>
            <div className="shrink-0">
              <StatusBadge status={employee.status} />
            </div>
          </CardContent>
        </Card>

        {/* Detail sections */}
        <div className="grid gap-4 lg:grid-cols-2">
          <DetailSection icon={Briefcase} title="Employee Information">
            <DetailField label="Employee ID" value={employee.employee_code} />
            <DetailField label="Department" value={employee.department} />
            <DetailField label="Designation" value={employee.designation} />
            <DetailField label="Office" value={employee.office_name} />
            <DetailField
              label="Join Date"
              value={formatJoinDate(employee.date_of_joining)}
            />
          </DetailSection>

          <DetailSection icon={Mail} title="Contact Information">
            <DetailField label="Company Email" value={employee.work_email} />
            <DetailField label="Personal Email" value={employee.personal_email} />
            <DetailField label="Phone" value={employee.phone} />
          </DetailSection>

          <DetailSection
            icon={Users}
            title="Reporting Structure"
            className="lg:col-span-2"
          >
            <DetailField label="Reporting Manager" value={employee.manager_name} />
          </DetailSection>
        </div>
      </div>
    </>
  );
}
