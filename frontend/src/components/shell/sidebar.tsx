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

import { Brand, LogoMark } from "@/components/shell/brand";
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
  // animates between 72px and 240px. Both variants share the same h-10 row
  // height so items don't shift vertically when the rail toggles.
  const base = collapsed
    ? "relative mx-auto flex h-10 w-10 items-center justify-center rounded-md transition-colors"
    : "flex h-10 items-center gap-3 overflow-hidden whitespace-nowrap rounded-md px-2.5 text-sm transition-colors";

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

// Only ever rendered in the expanded header — the collapsed rail's toggle is
// folded into the logo slot itself (see CollapsedBrandToggle).
function CollapseToggle({ onToggle }: { onToggle: () => void }) {
  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={onToggle}
      aria-label="Collapse sidebar"
      className="h-8 w-8 shrink-0 text-muted-foreground"
    >
      <PanelLeftClose className="h-5 w-5" strokeWidth={1.75} />
    </Button>
  );
}

// ChatGPT-style collapsed header control: one square slot that shows the CDC
// mark at rest and crossfades to the expand icon on hover/focus. Both layers
// are absolutely positioned over the same h-9 w-9 box, so nothing moves —
// only opacity changes.
function CollapsedBrandToggle({ onToggle }: { onToggle: () => void }) {
  const label = "Expand sidebar";

  const button = (
    <Button
      variant="ghost"
      size="icon"
      onClick={onToggle}
      aria-label={label}
      className="group relative h-9 w-9 shrink-0 text-muted-foreground"
    >
      <span
        aria-hidden
        className="absolute inset-0 flex items-center justify-center opacity-100 transition-opacity duration-150 motion-reduce:transition-none group-hover:opacity-0 group-focus-visible:opacity-0"
      >
        <LogoMark height={22} />
      </span>
      <span
        aria-hidden
        className="absolute inset-0 flex items-center justify-center opacity-0 transition-opacity duration-150 motion-reduce:transition-none group-hover:opacity-100 group-focus-visible:opacity-100"
      >
        <PanelLeftOpen className="h-5 w-5" strokeWidth={1.75} />
      </span>
    </Button>
  );

  return (
    <Tooltip>
      <TooltipTrigger asChild>{button}</TooltipTrigger>
      <TooltipContent side="right">{label}</TooltipContent>
    </Tooltip>
  );
}

function SidebarHeader({
  collapsed,
  onToggleCollapsed,
}: {
  collapsed: boolean;
  onToggleCollapsed?: () => void;
}) {
  // h-14 matches TopNav's own h-14 (top-nav.tsx) exactly, and both start at
  // the same grid row, so the two border-bottoms — and the vertical centre of
  // everything in each row — line up without any margin/translate faking it.
  if (collapsed && onToggleCollapsed) {
    return (
      <div className="flex h-14 shrink-0 items-center justify-center border-b border-border px-2">
        <CollapsedBrandToggle onToggle={onToggleCollapsed} />
      </div>
    );
  }

  return (
    <div className="flex h-14 shrink-0 items-center justify-between gap-2 border-b border-border px-3">
      {/* Fixed logoHeight (independent of `collapsed`) keeps the mark the same
          compact size in both states — only the wordmark appears/disappears. */}
      <Brand markOnly={collapsed} logoHeight={22} />
      {onToggleCollapsed && <CollapseToggle onToggle={onToggleCollapsed} />}
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

  return (
    <nav className="flex h-full flex-col border-r border-border bg-secondary/40">
      {/* The header owns no inherited padding — it sits flush against the nav's
          edges (h-full stretch), which is what keeps its border-bottom at the
          same y-position as TopNav's regardless of the collapsed/expanded
          padding below it. */}
      <SidebarHeader collapsed={collapsed} onToggleCollapsed={onToggleCollapsed} />

      {/* Fixed pt-3 + gap-1, independent of `collapsed`, so nav items start at
          the same offset and keep the same spacing in both rail widths. Only
          the side/bottom padding changes with the rail width. */}
      <div
        className={cn(
          "flex flex-1 flex-col gap-1 pt-3",
          collapsed ? "px-2 pb-2" : "px-3 pb-3",
        )}
      >
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
            <div className="my-1 border-t border-border" aria-hidden />
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
      </div>
    </nav>
  );
}
