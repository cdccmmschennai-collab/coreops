import Image from "next/image";

import cdcLogo from "@/assets/cdc-logo.png";
import { env } from "@/lib/env";
import { cn } from "@/lib/utils";

interface BrandProps {
  className?: string;
  /** Rendered logo height in px; width scales to preserve the source aspect ratio. */
  logoHeight?: number;
  /** Mark only, no wordmark — used by the collapsed sidebar rail. */
  markOnly?: boolean;
}

/**
 * Product mark + wordmark on a single horizontal row. The mark is the CDC
 * company logo; the name comes from one token only (D-001). next/image keeps the
 * source aspect ratio intact and the original asset (242px wide) stays crisp on
 * high-DPI displays when downscaled in CSS.
 *
 * The wordmark is clipped rather than wrapped while the sidebar animates between
 * widths, so it never reflows mid-transition.
 */
export function Brand({ className, logoHeight = 28, markOnly = false }: BrandProps) {
  const width = Math.round((logoHeight * cdcLogo.width) / cdcLogo.height);
  return (
    <div
      className={cn(
        "flex flex-row items-center gap-2",
        markOnly && "justify-center",
        className,
      )}
    >
      <Image
        src={cdcLogo}
        alt="CDC"
        width={width}
        height={logoHeight}
        priority
        unoptimized
        className="shrink-0 object-contain"
        style={{ width, height: logoHeight }}
      />
      {!markOnly && (
        <span className="whitespace-nowrap font-semibold tracking-tight text-foreground">
          {env.productName}
        </span>
      )}
    </div>
  );
}
