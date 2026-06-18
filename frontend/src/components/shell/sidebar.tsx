"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Bell,
  CalendarDays,
  FolderKanban,
  Home,
  Users,
  FileText,
  ListTodo,
  Settings,
  type LucideIcon,
} from "lucide-react";

import { Brand } from "@/components/shell/brand";
import { useAuth } from "@/features/auth/auth-provider";
import { useUnreadCount } from "@/features/notifications/hooks";
import { can, type Capability } from "@/lib/rbac";
import { cn } from "@/lib/utils";

interface NavItem {
  label: string;
  href: string;
  icon: LucideIcon;
  capability?: Capability;
  soon?: boolean;
  count?: number;
  alsoMatch?: string[];
}

const WORKSPACE: NavItem[] = [
  { label: "Home",          href: "/dashboard",     icon: Home },
  { label: "Employees",     href: "/employees",     icon: Users,        capability: "employee.view" },
  { label: "Projects",      href: "/projects",      icon: FolderKanban, capability: "project.view" },
  { label: "Attendance",    href: "/attendance",    icon: CalendarDays },
  { label: "Tasks",         href: "/tasks",         icon: ListTodo,     capability: "task.view", alsoMatch: ["/tasks/all"] },
  { label: "Reports",       href: "/reports",       icon: FileText,     capability: "report.nav", alsoMatch: ["/work-reports"] },
  { label: "Notifications", href: "/notifications", icon: Bell },
];

const MANAGE: NavItem[] = [
  { label: "Settings", href: "/settings", icon: Settings },
];

function NavLink({ item, active }: { item: NavItem; active: boolean }) {
  const Icon = item.icon;
  const base =
    "flex items-center gap-3 rounded-md px-2.5 py-2 text-sm transition-colors";
  if (item.soon) {
    return (
      <span
        className={cn(base, "cursor-not-allowed text-muted-foreground/60")}
        title="Coming soon"
        aria-disabled
      >
        <Icon className="h-4 w-4" strokeWidth={1.75} />
        <span>{item.label}</span>
        <span className="ml-auto text-[10px] uppercase tracking-wide text-muted-foreground/60">
          soon
        </span>
      </span>
    );
  }
  return (
    <Link
      href={item.href}
      className={cn(
        base,
        active
          ? "bg-accent font-medium text-primary"
          : "text-foreground hover:bg-secondary",
      )}
    >
      <Icon className="h-4 w-4" strokeWidth={1.75} />
      <span>{item.label}</span>
      {item.count != null && item.count > 0 && (
        <span className="ml-auto rounded-full bg-primary px-1.5 py-0.5 text-[10px] font-bold leading-none text-primary-foreground">
          {item.count > 99 ? "99+" : item.count}
        </span>
      )}
    </Link>
  );
}

export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const { role } = useAuth();
  const { data: unreadData } = useUnreadCount();
  const unreadCount = unreadData?.count ?? 0;

  const visibleWorkspace = WORKSPACE.filter(
    (item) => !item.capability || can(role, item.capability),
  ).map((item) =>
    item.href === "/notifications" ? { ...item, count: unreadCount } : item
  );

  return (
    <nav
      className="flex h-full flex-col gap-1 border-r border-border bg-secondary/40 p-3"
      onClick={onNavigate}
    >
      <div className="px-1.5 pb-3 pt-1">
        <Brand />
      </div>

      <p className="px-2.5 pb-1 pt-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        Workspace
      </p>
      {visibleWorkspace.map((item) => (
        <NavLink
          key={item.href}
          item={item}
          active={
            pathname === item.href ||
            pathname.startsWith(`${item.href}/`) ||
            (item.alsoMatch?.some(
              (p) => pathname === p || pathname.startsWith(`${p}/`)
            ) ?? false)
          }
        />
      ))}

      {can(role, "user.manage") && (
        <>
          <p className="px-2.5 pb-1 pt-3 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            Manage
          </p>
          {MANAGE.map((item) => (
            <NavLink
              key={item.href}
              item={item}
              active={pathname === item.href}
            />
          ))}
        </>
      )}
    </nav>
  );
}
