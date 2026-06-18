"use client";

import * as React from "react";
import { Suspense } from "react";
import { usePathname, useSearchParams } from "next/navigation";

import { RequireCapability } from "@/components/auth/require-capability";
import { PageHeader } from "@/components/shell/page-header";
import { Tabs } from "@/components/ui/tabs";
import { ActivityMasterManager } from "@/features/activity-master/components/activity-master-manager";
import { ActivityTypesManager } from "@/features/activity-types/components/activity-types-manager";
import { AuditLogView } from "@/features/audit/components/audit-log-view";
import { UsersView } from "@/features/users/components/users-view";

import { AdminCorrectionsPreview } from "./components/admin-corrections-preview";
import { LeaveApprovalsPreview } from "./components/leave-approvals-preview";
import { RolesTab } from "./components/roles-tab";
import { SsoPreview } from "./components/sso-preview";

type TabKey =
  | "users"
  | "roles"
  | "activity-master"
  | "activity-types"
  | "leave"
  | "corrections"
  | "audit"
  | "sso";

const TABS = [
  { value: "users",           label: "Users & Roles" },
  { value: "roles",           label: "Roles" },
  { value: "activity-master", label: "Activity Master" },
  { value: "activity-types",  label: "Activity Types (Legacy)" },
  { value: "leave",           label: "Leave approvals" },
  { value: "corrections",     label: "Attendance corrections",  count: 2 },
  { value: "audit",           label: "Audit log" },
  { value: "sso",             label: "SSO" },
];

function SettingsContent() {
  const pathname  = usePathname();
  const sp        = useSearchParams();
  // Read once on mount; subsequent switches are local state, not a router
  // navigation, so they don't trigger a server round-trip for every tab.
  const [tab, setTabState] = React.useState<TabKey>((sp.get("tab") ?? "users") as TabKey);

  function setTab(next: string) {
    setTabState(next as TabKey);
    const p = new URLSearchParams();
    if (next !== "users") p.set("tab", next);
    const qs = p.toString();
    window.history.replaceState(null, "", qs ? `${pathname}?${qs}` : pathname);
  }

  return (
    <RequireCapability capability="user.manage">
      <PageHeader
        title="Settings"
        subtitle="Manage workspace members, roles, and integrations."
      />
      <Tabs className="mb-4" value={tab} onChange={setTab} items={TABS} />

      {tab === "users"           && <Suspense><UsersView hideHeader /></Suspense>}
      {tab === "roles"           && <RolesTab />}
      {tab === "activity-master" && <ActivityMasterManager />}
      {tab === "activity-types"  && <ActivityTypesManager />}
      {tab === "leave"           && <LeaveApprovalsPreview />}
      {tab === "corrections"     && <AdminCorrectionsPreview />}
      {tab === "audit"           && <AuditLogView />}
      {tab === "sso"             && <SsoPreview />}
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
