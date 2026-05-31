"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Plus } from "lucide-react";

import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/features/auth/auth-provider";
import { can } from "@/lib/rbac";

import { UsersFilters, type UserFilterValues } from "./users-filters";
import { UsersTable } from "./users-table";
import { useUsersList } from "../hooks";
import { USER_ROLES } from "../schemas";
import type { UserListParams, UserPage, UserRole } from "../types";

const LIMIT = 20;

function parseRole(value: string | null): UserRole | "" {
  return value && (USER_ROLES as readonly string[]).includes(value) ? (value as UserRole) : "";
}

export function UsersView() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { role } = useAuth();
  const canManage = can(role, "user.manage");

  const q = searchParams.get("q") ?? "";
  // Role is filtered client-side (the /users API exposes only q/limit/offset).
  const roleFilter = parseRole(searchParams.get("role"));

  const params: UserListParams = {
    q,
    limit: LIMIT,
    offset: Math.max(0, Number(searchParams.get("offset") ?? "0") || 0),
  };

  const query = useUsersList(params);

  function commit(next: URLSearchParams) {
    const qs = next.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname);
  }

  function onFilterChange(patch: Partial<UserFilterValues>) {
    const next = new URLSearchParams(searchParams.toString());
    for (const [key, value] of Object.entries(patch)) {
      if (value) next.set(key, value);
      else next.delete(key);
    }
    next.delete("offset"); // back to first page when filters change
    commit(next);
  }

  function onPageChange(offset: number) {
    const next = new URLSearchParams(searchParams.toString());
    if (offset > 0) next.set("offset", String(offset));
    else next.delete("offset");
    commit(next);
  }

  // Client-side role filter over the current page (no server-side role param).
  const data: UserPage | undefined = query.data
    ? roleFilter
      ? { ...query.data, items: query.data.items.filter((u) => u.role === roleFilter) }
      : query.data
    : undefined;

  const addButton = canManage ? (
    <Button asChild>
      <Link href="/settings/new">
        <Plus className="h-4 w-4" />
        Add user
      </Link>
    </Button>
  ) : null;

  const count = query.data?.total;

  return (
    <>
      <PageHeader
        title="Users & Roles"
        subtitle={count !== undefined ? `${count} ${count === 1 ? "user" : "users"}` : undefined}
        actions={addButton}
      />
      <div className="mb-4">
        <UsersFilters values={{ q, role: roleFilter }} onChange={onFilterChange} />
      </div>
      <UsersTable
        data={data}
        isLoading={query.isLoading}
        isError={query.isError}
        onRetry={() => void query.refetch()}
        onPageChange={onPageChange}
        canManage={canManage}
        emptyAction={addButton}
      />
    </>
  );
}
