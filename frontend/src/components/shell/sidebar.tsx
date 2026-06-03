"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BarChart3,
  CalendarDays,
  FolderKanban,
  Home,
  Users,
  FileText,
  Settings,
  type LucideIcon,
} from "lucide-react";

import { Brand } from "@/components/shell/brand";
import { useAuth } from "@/features/auth/auth-provider";
import { can } from "@/lib/rbac";
import { cn } from "@/lib/utils";

interface NavItem {
  label: string;
  href: string;
  icon: LucideIcon;
  /** Page not built yet (F2+). Rendered disabled so the shell looks complete. */
  soon?: boolean;
}

const WORKSPACE: NavItem[] = [
  { label: "Home", href: "/dashboard", icon: Home },
  { label: "Employees", href: "/employees", icon: Users },
  { label: "Projects", href: "/projects", icon: FolderKanban },
  { label: "Attendance", href: "/attendance", icon: CalendarDays },
  { label: "Reports", href: "/reports", icon: FileText },
  { label: "Analytics", href: "/analytics", icon: BarChart3 },
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
    </Link>
  );
}

export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const { role } = useAuth();

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
      {WORKSPACE.map((item) => (
        <NavLink
          key={item.href}
          item={item}
          active={pathname === item.href || pathname.startsWith(`${item.href}/`)}
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
