"use client";

import { SearchInput } from "@/components/data/search-input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import { USER_ROLES, USER_ROLE_LABEL } from "../schemas";
import type { UserRole } from "../types";

export interface UserFilterValues {
  q: string;
  role: UserRole | "";
}

const ALL = "all";

export function UsersFilters({
  values,
  onChange,
}: {
  values: UserFilterValues;
  onChange: (patch: Partial<UserFilterValues>) => void;
}) {
  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
      <SearchInput
        className="sm:w-64"
        value={values.q}
        onChange={(q) => onChange({ q })}
        placeholder="Search email…"
      />
      <Select
        value={values.role === "" ? ALL : values.role}
        onValueChange={(v) => onChange({ role: v === ALL ? "" : (v as UserRole) })}
      >
        <SelectTrigger className="sm:w-44">
          <SelectValue placeholder="Role" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ALL}>All roles</SelectItem>
          {USER_ROLES.map((r) => (
            <SelectItem key={r} value={r}>
              {USER_ROLE_LABEL[r]}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
