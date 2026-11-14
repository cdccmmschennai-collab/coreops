/**
 * Loop-free "back" from the Deliverable Details page.
 *
 * When the list opens a deliverable it records, in THIS tab's sessionStorage,
 * that the details page has the list directly behind it in history. The back
 * link (and Delete) then call `history.back()` instead of pushing a new list
 * entry, so the browser history stays `list -> details` and the browser's own
 * Back button never ping-pongs between the two pages.
 *
 * With no record (a notification, the reminder banner, a pasted link or a new
 * tab) there is no list behind us, so the caller replaces the details entry
 * with the list instead - again without growing history.
 *
 * sessionStorage is per tab, so a link copied into another tab never pretends
 * to have history. Every access is guarded: blocked storage = "no record".
 */
const KEY_PREFIX = "deliverable-return:";

export function rememberListReturn(deliverableId: string): void {
  try {
    window.sessionStorage.setItem(KEY_PREFIX + deliverableId, "1");
  } catch {
    /* storage unavailable - fall back to replace navigation */
  }
}

export function cameFromList(deliverableId: string): boolean {
  try {
    return window.sessionStorage.getItem(KEY_PREFIX + deliverableId) === "1";
  } catch {
    return false;
  }
}

export function forgetListReturn(deliverableId: string): void {
  try {
    window.sessionStorage.removeItem(KEY_PREFIX + deliverableId);
  } catch {
    /* ignore */
  }
}

/**
 * Leave the details page without adding a history entry: go back when the
 * list is behind us, otherwise replace this entry with `fallbackHref`.
 */
export function leaveDetail(
  deliverableId: string,
  fallbackHref: string,
  nav: { back: () => void; replace: (href: string) => void },
): void {
  const back = cameFromList(deliverableId);
  forgetListReturn(deliverableId);
  if (back) nav.back();
  else nav.replace(fallbackHref);
}
