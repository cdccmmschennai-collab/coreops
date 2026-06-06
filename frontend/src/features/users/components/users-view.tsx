"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { PageHeader } from "@/components/shell/page-header";

import { UsersFilters, type UserFilterValues } from "./users-filters";
import { UsersTable } from "./users-table";
import { useUsersList } from "../hooks";
import { USER_ROLES } from "../schemas";
import type { UserListParams, UserPage, UserRole } from "../types";

const LIMIT = 20;

function parseRole(value: string | null): UserRole | "" {
  return value && (USER_ROLES as readonly string[]).includes(value) ? (value as UserRole) : "";
}

export function UsersView({ hideHeader = false }: { hideHeader?: boolean }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

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

  const count = query.data?.total;

  return (
    <>
      {!hideHeader && (
        <PageHeader
          title="Users & Roles"
          subtitle={count !== undefined ? `${count} ${count === 1 ? "user" : "users"}` : undefined}
        />
      )}
      <div className="mb-4">
        <UsersFilters values={{ q, role: roleFilter }} onChange={onFilterChange} />
      </div>
      <UsersTable
        data={data}
        isLoading={query.isLoading}
        isError={query.isError}
        onRetry={() => void query.refetch()}
        onPageChange={onPageChange}
      />
    </>
  );
}
