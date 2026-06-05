"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { LogOut, Menu, Settings, User as UserIcon } from "lucide-react";
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
import { USER_ROLE_LABEL } from "@/features/users/schemas";
import { NotificationBell } from "@/features/notifications/components/notification-bell";
import { emailInitials, nameInitials } from "@/lib/initials";

export function TopNav({ onToggleSidebar }: { onToggleSidebar: () => void }) {
  const { user, employee, role, logout } = useAuth();
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
            <DropdownMenuContent align="end" className="min-w-[256px]">
              <DropdownMenuLabel className="font-normal">
                {employee ? (
                  <div className="flex items-center gap-3">
                    <Avatar className="h-10 w-10">
                      <AvatarFallback>{nameInitials(employee.full_name)}</AvatarFallback>
                    </Avatar>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold">
                        {employee.full_name}
                      </p>
                      <p className="truncate text-xs text-muted-foreground">
                        {[employee.employee_code, employee.designation]
                          .filter(Boolean)
                          .join(" · ")}
                      </p>
                    </div>
                  </div>
                ) : (
                  <div className="flex items-center gap-3">
                    <Avatar className="h-10 w-10">
                      <AvatarFallback>{emailInitials(user.email)}</AvatarFallback>
                    </Avatar>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">{user.email}</p>
                      <p className="truncate text-xs capitalize text-muted-foreground">
                        {role ? (USER_ROLE_LABEL[role] ?? role) : "—"}
                      </p>
                    </div>
                  </div>
                )}
              </DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem asChild>
                <Link href="/profile">
                  <UserIcon className="h-4 w-4" />
                  My Profile
                </Link>
              </DropdownMenuItem>
              <DropdownMenuItem asChild>
                <Link href="/account">
                  <Settings className="h-4 w-4" />
                  Account Settings
                </Link>
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={handleLogout}>
                <LogOut className="h-4 w-4" />
                Logout
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        )}
      </div>
    </header>
  );
}
