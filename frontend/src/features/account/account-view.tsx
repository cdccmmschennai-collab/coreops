"use client";

import Link from "next/link";
import { KeyRound, ShieldCheck } from "lucide-react";

import { DetailField, DetailSection } from "@/components/data/detail-section";
import { BackButton } from "@/components/shell/back-button";
import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/features/auth/auth-provider";
import { RoleBadge } from "@/features/users/components/role-badge";
import { UserStatusBadge } from "@/features/users/components/user-status-badge";
import { formatDateTime } from "@/lib/format";

export function AccountView() {
  const { user, employee } = useAuth();

  if (!user) return null;

  const linkedEmployee = employee ? (
    <Link href="/profile" className="text-primary hover:underline">
      {employee.full_name} ({employee.employee_code})
    </Link>
  ) : (
    "Not linked"
  );

  return (
    <>
      <BackButton fallback="/" />
      <PageHeader
        title="Account Settings"
        subtitle="Your sign-in identity and account status. This page is read-only."
      />

      <div className="max-w-4xl space-y-4">
        <DetailSection icon={ShieldCheck} title="Account">
          <DetailField label="Login Email" value={user.email} />
          <DetailField label="Role" value={<RoleBadge role={user.role} />} />
          <DetailField
            label="Account Status"
            value={<UserStatusBadge active={user.is_active} />}
          />
          <DetailField label="Last Login" value={formatDateTime(user.last_login_at)} />
          <DetailField label="Linked Employee" value={linkedEmployee} />
        </DetailSection>

        <DetailSection
          icon={KeyRound}
          title="Security"
          action={
            <Button variant="secondary" size="sm" asChild>
              <Link href="/account/change-password">
                <KeyRound className="h-4 w-4" />
                Change Password
              </Link>
            </Button>
          }
        >
          <DetailField label="Password" value="••••••••" />
        </DetailSection>
      </div>
    </>
  );
}
