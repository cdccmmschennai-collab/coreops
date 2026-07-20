/**
 * Desktop sidebar preference — pure state helpers (no React, no DOM).
 *
 * The preference is per-user: two people sharing a computer each keep their own
 * collapsed/expanded choice, so every read and write is namespaced by a stable
 * identifier. When no identifier is available the sidebar still works for the
 * session but nothing is persisted — writing to a shared anonymous key would
 * leak one user's preference to the next.
 *
 * Everything here is deliberately free of `window` so it can be unit-tested
 * with the repo's node:test runner (there is no DOM test framework).
 */

/** Key prefix. Bump only alongside a change to the stored representation. */
export const SIDEBAR_STORAGE_PREFIX = "coreops.sidebar.collapsed";

/**
 * The viewport band that defaults to collapsed. Below the minimum the mobile
 * drawer takes over (this preference is stored but unused); above the maximum
 * there is room to stay expanded.
 */
export const NARROW_DESKTOP_MIN = 861;
export const NARROW_DESKTOP_MAX = 1100;

/** Media query for the band above — derived from the constants so the two
 *  can never drift apart. */
export const NARROW_DESKTOP_QUERY =
  `(min-width: ${NARROW_DESKTOP_MIN}px) and (max-width: ${NARROW_DESKTOP_MAX}px)`;

/** Identifier sources, in the order they should be preferred. */
export interface UserIdentitySources {
  /** Authenticated user row id — the most stable option. */
  userId?: string | null;
  /** Employee row id (present for staff accounts). */
  employeeId?: string | null;
  /** Human-facing employee code, e.g. "EMP225". */
  employeeCode?: string | null;
}

/**
 * The first stable identifier available: user id, then employee id, then
 * employee code. Display name and email are deliberately NOT used — both can
 * change while identifying the same person, which would silently orphan the
 * stored preference.
 *
 * Returns null when nothing usable is present (blank strings included).
 */
export function pickUserIdentifier(sources: UserIdentitySources): string | null {
  for (const candidate of [sources.userId, sources.employeeId, sources.employeeCode]) {
    const trimmed = candidate?.trim();
    if (trimmed) return trimmed;
  }
  return null;
}

/**
 * The localStorage key for one user, or null when there is no identifier to
 * namespace it with. A null key means "session-only": callers must skip both
 * the read and the write rather than fall back to a shared key.
 */
export function sidebarStorageKey(identifier: string | null | undefined): string | null {
  const trimmed = identifier?.trim();
  return trimmed ? `${SIDEBAR_STORAGE_PREFIX}:${trimmed}` : null;
}

/**
 * Parse a stored value into a preference, or null when there is no usable one.
 *
 * Only the exact strings "true" and "false" count. Anything else — absent,
 * empty, legacy JSON, a half-written value, or something another tab wrote —
 * is treated as "no preference" so the viewport default applies instead of a
 * guess.
 */
export function parseStoredCollapsed(raw: string | null | undefined): boolean | null {
  if (raw === "true") return true;
  if (raw === "false") return false;
  return null;
}

/** Serialise a preference. Kept beside the parser so the two stay symmetrical. */
export function serializeCollapsed(collapsed: boolean): string {
  return collapsed ? "true" : "false";
}

/**
 * The viewport default when the user has expressed no preference: collapsed in
 * the narrow-desktop band, expanded otherwise. Below NARROW_DESKTOP_MIN the
 * mobile drawer is in charge, so the value is irrelevant there and reports
 * expanded.
 */
export function defaultCollapsedForWidth(width: number): boolean {
  return width >= NARROW_DESKTOP_MIN && width <= NARROW_DESKTOP_MAX;
}

/**
 * The initial collapsed value: a saved preference always wins; the viewport
 * default applies only when there is none (or the stored value is unusable).
 */
export function resolveInitialCollapsed(
  stored: string | null | undefined,
  viewportCollapsed: boolean,
): boolean {
  return parseStoredCollapsed(stored) ?? viewportCollapsed;
}
