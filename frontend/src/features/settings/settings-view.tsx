"use client";

import * as React from "react";
import { Suspense } from "react";
import { usePathname, useSearchParams } from "next/navigation";

import { RequireCapability } from "@/components/auth/require-capability";
import { PageHeader } from "@/components/shell/page-header";
import { Tabs } from "@/components/ui/tabs";
import { ActivityMasterManager } from "@/features/activity-master/components/activity-master-manager";
import { AuditLogView } from "@/features/audit/components/audit-log-view";
import { UsersView } from "@/features/users/components/users-view";

import { RolesTab } from "./components/roles-tab";

type TabKey =
  | "users"
  | "roles"
  | "activity-master"
  | "audit";

const TABS = [
  { value: "users",           label: "Users & Roles" },
  { value: "roles",           label: "Roles" },
  { value: "activity-master", label: "Activity Master" },
  { value: "audit",           label: "Audit log" },
];

function SettingsContent() {
  const pathname  = usePathname();
  const sp        = useSearchParams();
  // Read once on mount; subsequent switches are local state, not a router
  // navigation, so they don't trigger a server round-trip for every tab. A stale
  // tab from a bookmarked URL (e.g. a removed tab) falls back to "users".
  const [tab, setTabState] = React.useState<TabKey>(() => {
    const requested = sp.get("tab");
    return TABS.some((t) => t.value === requested) ? (requested as TabKey) : "users";
  });

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
      {tab === "audit"           && <AuditLogView />}
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
