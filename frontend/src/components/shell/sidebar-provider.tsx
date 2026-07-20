"use client";

/**
 * Desktop sidebar preference (expanded / collapsed), persisted per user.
 *
 * PHASE 2: state foundation only. Nothing consumes `collapsed` yet, so the
 * rendered shell is byte-for-byte unchanged — the grid columns, the 240px
 * sidebar and every nav control still look exactly as they did.
 *
 * Scope: DESKTOP preference only. MobileNavDrawer keeps its own local open
 * state; the two are different concerns (a transient overlay vs. a durable
 * layout preference) and merging them would couple an ephemeral UI toggle to
 * per-user persistence.
 *
 * Hydration: this provider is mounted inside the authenticated `(app)` layout,
 * which renders <FullScreenLoader /> until `useAuth().status === "authenticated"`.
 * AuthProvider reports "loading" until its own mount effect runs, so on the
 * server that gate ALWAYS renders the loader — this subtree never appears in
 * the server HTML. Its first render is therefore client-side and post-auth,
 * which is what makes reading localStorage and matchMedia in the state
 * initialiser safe: there is no server-rendered markup for it to mismatch, and
 * no second pass that could flash the wrong width once a later phase starts
 * applying `collapsed` to the layout.
 */

import * as React from "react";

import { useAuth } from "@/features/auth/auth-provider";

import {
  NARROW_DESKTOP_QUERY,
  pickUserIdentifier,
  resolveInitialCollapsed,
  serializeCollapsed,
  sidebarStorageKey,
} from "./sidebar-state";

interface SidebarContextValue {
  /** Whether the desktop sidebar is collapsed. */
  collapsed: boolean;
  setCollapsed: (value: boolean) => void;
  toggleCollapsed: () => void;
}

const SidebarContext = React.createContext<SidebarContextValue | null>(null);

/** localStorage access that never throws — Safari private mode, disabled
 *  storage and quota errors all degrade to "no stored preference". */
function safeRead(key: string | null): string | null {
  if (!key || typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function safeWrite(key: string | null, value: string): void {
  if (!key || typeof window === "undefined") return;
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Preference is session-only when storage is unavailable. Never fatal.
  }
}

/** The viewport default, read once. Falls back to expanded wherever
 *  matchMedia is unavailable. */
function viewportDefaultCollapsed(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return false;
  }
  try {
    return window.matchMedia(NARROW_DESKTOP_QUERY).matches;
  } catch {
    return false;
  }
}

export function SidebarProvider({ children }: { children: React.ReactNode }) {
  const { user, employeeId, employee } = useAuth();

  // user.id -> employee id -> employee code. Null only if auth somehow yields
  // none of the three; the sidebar then works for the session but persists
  // nothing rather than writing to a key shared with the next user.
  const storageKey = sidebarStorageKey(
    pickUserIdentifier({
      userId: user?.id,
      employeeId,
      employeeCode: employee?.employee_code,
    }),
  );

  // Lazy initialiser: runs once, on the client, with the identifier already
  // resolved (see the hydration note above) — so the correct value is present
  // on the very first paint.
  const [collapsed, setCollapsedState] = React.useState<boolean>(() =>
    resolveInitialCollapsed(safeRead(storageKey), viewportDefaultCollapsed()),
  );

  // Keep the key in a ref so the callbacks below stay referentially stable.
  const storageKeyRef = React.useRef(storageKey);

  React.useEffect(() => {
    const previous = storageKeyRef.current;
    if (previous === storageKey) return;
    storageKeyRef.current = storageKey;
    if (previous === null && storageKey !== null) {
      // The identifier arrived after mount: keep what the user is looking at
      // and adopt it as their preference rather than resetting under them.
      safeWrite(storageKey, serializeCollapsed(collapsed));
      return;
    }
    // A different user (or sign-out): load THEIR preference.
    setCollapsedState(
      resolveInitialCollapsed(safeRead(storageKey), viewportDefaultCollapsed()),
    );
  }, [storageKey, collapsed]);

  // Persisted on explicit user action only. Writing the computed default on
  // mount would freeze the first session's viewport into a stored preference,
  // making a genuine choice indistinguishable from a default.
  const setCollapsed = React.useCallback((value: boolean) => {
    setCollapsedState(value);
    safeWrite(storageKeyRef.current, serializeCollapsed(value));
  }, []);

  const toggleCollapsed = React.useCallback(() => {
    setCollapsedState((prev) => {
      const next = !prev;
      safeWrite(storageKeyRef.current, serializeCollapsed(next));
      return next;
    });
  }, []);

  const value = React.useMemo(
    () => ({ collapsed, setCollapsed, toggleCollapsed }),
    [collapsed, setCollapsed, toggleCollapsed],
  );

  return (
    <SidebarContext.Provider value={value}>{children}</SidebarContext.Provider>
  );
}

export function useSidebar(): SidebarContextValue {
  const ctx = React.useContext(SidebarContext);
  if (!ctx) throw new Error("useSidebar must be used within <SidebarProvider>");
  return ctx;
}
