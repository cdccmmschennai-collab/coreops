"use client";

import * as React from "react";
import { Suspense } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { RequireCapability } from "@/components/auth/require-capability";
import { PageHeader } from "@/components/shell/page-header";
import { Tabs } from "@/components/ui/tabs";
import { UsersView } from "@/features/users/components/users-view";

import { AdminCorrectionsPreview } from "./components/admin-corrections-preview";
import { AuditLogPreview } from "./components/audit-log-preview";
import { LeaveApprovalsPreview } from "./components/leave-approvals-preview";
import { RolesTab } from "./components/roles-tab";
import { SsoPreview } from "./components/sso-preview";

type TabKey = "users" | "roles" | "leave" | "corrections" | "audit" | "sso";

const TABS = [
  { value: "users",       label: "Users & Roles" },
  { value: "roles",       label: "Roles" },
  { value: "leave",       label: "Leave approvals",         count: 4 },
  { value: "corrections", label: "Attendance corrections",  count: 2 },
  { value: "audit",       label: "Audit log" },
  { value: "sso",         label: "SSO" },
];

function SettingsContent() {
  const router    = useRouter();
  const pathname  = usePathname();
  const sp        = useSearchParams();
  const tab       = (sp.get("tab") ?? "users") as TabKey;

  function setTab(next: string) {
    const p = new URLSearchParams();
    if (next !== "users") p.set("tab", next);
    const qs = p.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname);
  }

  return (
    <RequireCapability capability="user.manage">
      <PageHeader
        title="Settings"
        subtitle="Manage workspace members, roles, and integrations."
      />
      <Tabs className="mb-4" value={tab} onChange={setTab} items={TABS} />

      {tab === "users"       && <Suspense><UsersView hideHeader /></Suspense>}
      {tab === "roles"       && <RolesTab />}
      {tab === "leave"       && <LeaveApprovalsPreview />}
      {tab === "corrections" && <AdminCorrectionsPreview />}
      {tab === "audit"       && <AuditLogPreview />}
      {tab === "sso"         && <SsoPreview />}
    </RequireCapability>
  );
}

export function SettingsView() {
  return (
    <Suspense>
      <SettingsContent />
    </Suspense>
  );
}
