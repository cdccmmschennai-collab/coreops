import type { components } from "@/types/openapi";

// Types come straight from the live API contract (openapi-typescript output).
export type User = components["schemas"]["UserOut"];
export type UserListItem = components["schemas"]["UserListItem"];
export type LinkedEmployee = components["schemas"]["LinkedEmployee"];
export type UserRole = components["schemas"]["UserRole"];
export type UserPage = components["schemas"]["UserPage"];
export type UserCreateBody = components["schemas"]["UserCreate"];
export type UserUpdateBody = components["schemas"]["UserUpdate"];

export interface UserListParams {
  q: string;
  limit: number;
  offset: number;
}
