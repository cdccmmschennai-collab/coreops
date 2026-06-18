"use client";

import { useRouter } from "next/navigation";
import { ChevronLeft } from "lucide-react";

interface BackButtonProps {
  /** Explicit destination. When set, always navigates here instead of going back. */
  href?: string;
  /** Where to go when there is no browser history to return to. */
  fallback?: string;
  label?: string;
}

/**
 * Page-header back control. Prefers `router.back()` (returns to the previous
 * page); falls back to `fallback` when there's no in-app history (e.g. the page
 * was opened directly). Pass `href` to force a fixed destination.
 */
export function BackButton({ href, fallback = "/", label = "Back" }: BackButtonProps) {
  const router = useRouter();

  function handleClick() {
    if (href) {
      router.push(href);
      return;
    }
    if (typeof window !== "undefined" && window.history.length > 1) {
      router.back();
    } else {
      router.push(fallback);
    }
  }

  return (
    <button
      type="button"
      onClick={handleClick}
      className="mb-3 inline-flex items-center gap-1 rounded text-sm text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <ChevronLeft className="h-4 w-4" />
      {label}
    </button>
  );
}
