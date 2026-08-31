"use client";

import * as React from "react";
import { useSearchParams } from "next/navigation";

/**
 * Persist one piece of UI state — a filter value, search text, the active tab,
 * a page number — in the URL query string so it survives leaving the page for a
 * detail view and coming back.
 *
 * The value stays in local React state for instant, churn-free updates; every
 * change is mirrored to the URL with `history.replaceState` (no new history
 * entry, no router re-render/refetch), and the initial value is read back from
 * the URL on mount — so a freshly re-mounted page (e.g. after the browser Back
 * button) restores exactly what the user had. Same intent as the inline
 * `useSearchParams` pattern already used by employees-view / settings-view,
 * centralised so every filter screen behaves identically.
 *
 * The consuming component MUST sit under a <Suspense> boundary — that is
 * `useSearchParams`'s requirement; every page using this is wrapped accordingly.
 */
export function useUrlState(
  key: string,
  fallback: string,
): [string, (value: string) => void] {
  const searchParams = useSearchParams();
  // Read the initial value from the URL once (SSR-safe and consistent between
  // server and client, so no hydration mismatch).
  const [value, setValue] = React.useState(() => searchParams.get(key) ?? fallback);

  /**
   * Browser Back / Forward.
   *
   * A navigation that leaves the route unmounts this component and the initial
   * read above restores the state. A history move that stays ON the route does
   * not - the URL changes underneath a component that keeps its state - so the
   * page would keep rendering the previous tab/filter while the address bar said
   * otherwise, and Forward would be just as wrong.
   *
   * `popstate` is deliberately the trigger, and the live `window.location` is
   * deliberately the source. `popstate` fires ONLY for a real history move,
   * never for the `pushState`/`replaceState` this hook and the router make, so
   * this can never race a user's own click and revert it - which reading
   * `useSearchParams` here could, since Next applies those writes to the router
   * in a transition.
   */
  React.useEffect(() => {
    function syncFromUrl() {
      setValue(new URLSearchParams(window.location.search).get(key) ?? fallback);
    }
    window.addEventListener("popstate", syncFromUrl);
    return () => window.removeEventListener("popstate", syncFromUrl);
  }, [key, fallback]);

  const set = React.useCallback(
    (next: string) => {
      setValue(next);
      if (typeof window === "undefined") return;
      // Read the live URL (not a stale snapshot) so several updates fired in the
      // same handler compose instead of clobbering each other.
      const params = new URLSearchParams(window.location.search);
      if (next && next !== fallback) params.set(key, next);
      else params.delete(key);
      const qs = params.toString();
      window.history.replaceState(
        null,
        "",
        qs ? `${window.location.pathname}?${qs}` : window.location.pathname,
      );
    },
    [key, fallback],
  );

  return [value, set];
}
