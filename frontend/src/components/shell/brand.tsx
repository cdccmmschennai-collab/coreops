import { env } from "@/lib/env";
import { cn } from "@/lib/utils";

/** Product wordmark + mark. Name comes from one token only (D-001). */
export function Brand({ className }: { className?: string }) {
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <span className="flex h-7 w-7 items-center justify-center rounded-md bg-[hsl(228,62%,28%)]">
        <svg viewBox="0 0 32 32" width="16" height="16" aria-hidden>
          <rect x="7" y="18" width="4" height="8" rx="1" fill="#fff" />
          <rect x="14" y="13" width="4" height="13" rx="1" fill="#fff" />
          <rect x="21" y="8" width="4" height="18" rx="1" fill="#fff" />
        </svg>
      </span>
      <span className="font-semibold tracking-tight text-foreground">
        {env.productName}
      </span>
    </div>
  );
}
