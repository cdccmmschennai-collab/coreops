"use client";

import { useRouter } from "next/navigation";
import { LogOut, Menu, User as UserIcon } from "lucide-react";
import { toast } from "sonner";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useAuth } from "@/features/auth/auth-provider";
import { useEmployeeOptions } from "@/features/attendance/employee-options";
import { USER_ROLE_LABEL } from "@/features/users/schemas";
import { NotificationBell } from "@/features/notifications/components/notification-bell";

function nameInitials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  const letters = parts.length >= 2
    ? `${parts[0][0]}${parts[parts.length - 1][0]}`
    : name.slice(0, 2);
  return letters.toUpperCase();
}

function emailInitials(email: string): string {
  const name = email.split("@")[0] ?? email;
  const parts = name.split(/[.\-_]/).filter(Boolean);
  const letters = parts.length >= 2 ? `${parts[0][0]}${parts[1][0]}` : name.slice(0, 2);
  return letters.toUpperCase();
}

export function TopNav({ onToggleSidebar }: { onToggleSidebar: () => void }) {
  const { user, employeeId, role, logout } = useAuth();
  const { items: allEmployees } = useEmployeeOptions();
  const employee = employeeId
    ? (allEmployees.find((e) => e.id === employeeId) ?? null)
    : null;
  const router = useRouter();

  async function handleLogout() {
    await logout();
    toast.success("Signed out");
    router.replace("/login");
  }

  return (
    <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-border bg-card/80 px-4 backdrop-blur md:px-6">
      <Button
        variant="ghost"
        size="icon"
        className="md:hidden"
        onClick={onToggleSidebar}
        aria-label="Toggle navigation"
      >
        <Menu className="h-5 w-5" />
      </Button>

      <div className="ml-auto flex items-center gap-2">
        {user && <NotificationBell />}
        {user && (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                className="flex items-center gap-2 rounded-full outline-none focus-visible:ring-2 focus-visible:ring-ring"
                aria-label="Account menu"
              >
                <Avatar className="h-9 w-9">
                  <AvatarFallback>
                    {employee
                      ? nameInitials(employee.full_name)
                      : emailInitials(user.email)}
                  </AvatarFallback>
                </Avatar>
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="min-w-[220px]">
              <DropdownMenuLabel className="flex flex-col gap-0.5">
                {employee ? (
                  <>
                    <span className="truncate text-sm font-semibold">
                      {employee.full_name}
                    </span>
                    <span className="text-xs font-normal text-muted-foreground">
                      {employee.designation ?? employee.employee_code}
                    </span>
                    <span className="truncate text-xs font-normal text-muted-foreground">
                      {employee.work_email ?? user.email}
                    </span>
                  </>
                ) : (
                  <>
                    <span className="truncate text-sm">{user.email}</span>
                    <span className="text-xs font-normal capitalize text-muted-foreground">
                      {role ? (USER_ROLE_LABEL[role] ?? role) : "—"}
                    </span>
                  </>
                )}
              </DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem disabled>
                <UserIcon className="h-4 w-4" />
                Profile (soon)
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={handleLogout}>
                <LogOut className="h-4 w-4" />
                Sign out
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        )}
      </div>
    </header>
  );
}
