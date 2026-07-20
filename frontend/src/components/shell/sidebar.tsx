"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Bell,
  CalendarDays,
  FolderKanban,
  Home,
  PanelLeftClose,
  PanelLeftOpen,
  Users,
  FileText,
  Settings,
  type LucideIcon,
} from "lucide-react";

import { Brand } from "@/components/shell/brand";
import { isNavItemActive, type NavMatch } from "@/components/shell/nav-active";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useAuth } from "@/features/auth/auth-provider";
import { useUnreadCount } from "@/features/notifications/hooks";
import { can, type Capability } from "@/lib/rbac";
import { cn } from "@/lib/utils";

interface NavItem extends NavMatch {
  label: string;
  icon: LucideIcon;
  capability?: Capability;
  soon?: boolean;
  count?: number;
}

const WORKSPACE: NavItem[] = [
  { label: "Home",          href: "/dashboard",     icon: Home },
  { label: "Employees",     href: "/employees",     icon: Users,        capability: "employee.view" },
  { label: "Projects",      href: "/projects",      icon: FolderKanban, capability: "project.view" },
  { label: "Attendance",    href: "/attendance",    icon: CalendarDays },
  { label: "Reports",       href: "/reports",       icon: FileText,     capability: "report.nav", alsoMatch: ["/work-reports"] },
  { label: "Notifications", href: "/notifications", icon: Bell },
];

const MANAGE: NavItem[] = [
  { label: "Settings", href: "/settings", icon: Settings },
];

function CountBadge({ count, collapsed }: { count: number; collapsed: boolean }) {
  const text = count > 99 ? "99+" : count;
  if (collapsed) {
    return (
      <span
        aria-hidden
        className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 text-[10px] font-bold leading-none text-primary-foreground"
      >
        {text}
      </span>
    );
  }
  return (
    <span className="ml-auto rounded-full bg-primary px-1.5 py-0.5 text-[10px] font-bold leading-none text-primary-foreground">
      {text}
    </span>
  );
}

function NavLink({
  item,
  active,
  collapsed,
}: {
  item: NavItem;
  active: boolean;
  collapsed: boolean;
}) {
  const Icon = item.icon;
  const hasCount = item.count != null && item.count > 0;

  // Labels are clipped, never wrapped, so they cannot reflow while the rail
  // animates between 72px and 240px.
  const base = collapsed
    ? "relative mx-auto flex h-10 w-10 items-center justify-center rounded-md transition-colors"
    : "flex items-center gap-3 overflow-hidden whitespace-nowrap rounded-md px-2.5 py-2 text-sm transition-colors";

  if (item.soon) {
    return (
      <span
        className={cn(base, "cursor-not-allowed text-muted-foreground/60")}
        title="Coming soon"
        aria-disabled
      >
        <Icon className="h-4 w-4 shrink-0" strokeWidth={1.75} />
        {!collapsed && (
          <>
            <span>{item.label}</span>
            <span className="ml-auto text-[10px] uppercase tracking-wide text-muted-foreground/60">
              soon
            </span>
          </>
        )}
      </span>
    );
  }

  const link = (
    <Link
      href={item.href}
      aria-current={active ? "page" : undefined}
      // The visible label is gone when collapsed, so the name comes from here
      // rather than from the tooltip. It also has to carry the count, which the
      // label would otherwise override.
      aria-label={
        collapsed
          ? hasCount
            ? `${item.label} (${item.count})`
            : item.label
          : undefined
      }
      className={cn(
        base,
        active
          ? "bg-accent font-medium text-primary"
          : "text-foreground hover:bg-secondary",
      )}
    >
      <Icon
        className={cn("shrink-0", collapsed ? "h-5 w-5" : "h-4 w-4")}
        strokeWidth={1.75}
      />
      {!collapsed && <span>{item.label}</span>}
      {hasCount && <CountBadge count={item.count!} collapsed={collapsed} />}
    </Link>
  );

  if (!collapsed) return link;

  return (
    <Tooltip>
      <TooltipTrigger asChild>{link}</TooltipTrigger>
      <TooltipContent side="right">{item.label}</TooltipContent>
    </Tooltip>
  );
}

function CollapseToggle({
  collapsed,
  onToggle,
}: {
  collapsed: boolean;
  onToggle: () => void;
}) {
  const label = collapsed ? "Expand sidebar" : "Collapse sidebar";
  const Icon = collapsed ? PanelLeftOpen : PanelLeftClose;

  const button = (
    <Button
      variant="ghost"
      size="icon"
      onClick={onToggle}
      aria-label={label}
      className={cn("h-9 w-9 text-muted-foreground", collapsed && "mx-auto")}
    >
      <Icon className="h-5 w-5" strokeWidth={1.75} />
    </Button>
  );

  return (
    <div className={cn("mt-auto border-t border-border pt-2", !collapsed && "flex justify-end")}>
      {collapsed ? (
        <Tooltip>
          <TooltipTrigger asChild>{button}</TooltipTrigger>
          <TooltipContent side="right">{label}</TooltipContent>
        </Tooltip>
      ) : (
        button
      )}
    </div>
  );
}

interface SidebarProps {
  /** Desktop rail mode. The mobile drawer always renders expanded. */
  collapsed?: boolean;
  /** Supplied only where the collapse control belongs — never in the drawer. */
  onToggleCollapsed?: () => void;
}

export function Sidebar({ collapsed = false, onToggleCollapsed }: SidebarProps) {
  const pathname = usePathname();
  const { role } = useAuth();
  const { data: unreadData } = useUnreadCount();
  const unreadCount = unreadData?.count ?? 0;

  const visibleWorkspace = WORKSPACE.filter(
    (item) => !item.capability || can(role, item.capability),
  ).map((item) =>
    item.href === "/notifications" ? { ...item, count: unreadCount } : item
  );

  const heading = "px-2.5 pb-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground";

  return (
    <nav
      className={cn(
        "flex h-full flex-col gap-1 border-r border-border bg-secondary/40",
        collapsed ? "p-2" : "p-3",
      )}
    >
      <div className={cn("pb-3 pt-1", collapsed ? "px-0" : "px-1.5")}>
        <Brand markOnly={collapsed} />
      </div>

      {!collapsed && <p className={cn(heading, "pt-2")}>Workspace</p>}
      {visibleWorkspace.map((item) => (
        <NavLink
          key={item.href}
          item={item}
          active={isNavItemActive(pathname, item)}
          collapsed={collapsed}
        />
      ))}

      {can(role, "user.manage") && (
        <>
          {collapsed ? (
            <div className="mx-auto my-1 h-px w-8 bg-border" aria-hidden />
          ) : (
            <p className={cn(heading, "pt-3")}>Manage</p>
          )}
          {MANAGE.map((item) => (
            <NavLink
              key={item.href}
              item={item}
              active={pathname === item.href}
              collapsed={collapsed}
            />
          ))}
        </>
      )}

      {onToggleCollapsed && (
        <CollapseToggle collapsed={collapsed} onToggle={onToggleCollapsed} />
      )}
    </nav>
  );
}
