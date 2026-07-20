export interface NavMatch {
  href: string;
  /** Extra route prefixes that also light this item up, e.g. Reports owns /work-reports. */
  alsoMatch?: string[];
}

/**
 * Lives in its own module so the desktop sidebar and the mobile drawer share one
 * matcher, and so the rule is reachable from the .ts-only unit test runner.
 */
export function isNavItemActive(pathname: string, item: NavMatch): boolean {
  const matches = (base: string) =>
    pathname === base || pathname.startsWith(`${base}/`);

  return matches(item.href) || (item.alsoMatch?.some(matches) ?? false);
}
