/**
 * Login-reminder banners (pending reports, deliverables due) can be dismissed
 * with X, but only for the CURRENT login. The flag lives in sessionStorage,
 * which belongs to the browser tab, not the user - so it must be cleared on
 * every login and logout, or one dismissal would hide the banner for every
 * later login in that tab (including a different user's).
 */
export const LOGIN_BANNER_KEYS = {
  pendingReports: "pending-reports-banner-dismissed",
  deliverableDue: "deliverable-due-banner-dismissed",
} as const;

export function isBannerDismissed(key: string): boolean {
  try {
    return sessionStorage.getItem(key) === "1";
  } catch {
    return false;
  }
}

export function dismissBanner(key: string): void {
  try {
    sessionStorage.setItem(key, "1");
  } catch {
    /* storage unavailable - the banner hides for this render only */
  }
}

export function resetLoginBanners(): void {
  try {
    for (const key of Object.values(LOGIN_BANNER_KEYS)) sessionStorage.removeItem(key);
  } catch {
    /* storage unavailable - nothing to reset */
  }
}
