import * as React from "react";

import { cn } from "@/lib/utils";

const MAX_WIDTH = {
  default: "max-w-6xl",
  wide: "max-w-[1600px]",
  full: "",
} as const;

interface PageContainerProps extends React.HTMLAttributes<HTMLElement> {
  width?: keyof typeof MAX_WIDTH;
  as?: "div" | "main";
}

/**
 * Centred content column shared by the page body and any full-bleed strip that
 * has to line up with it (e.g. the compliance banner). Keeping the cap in one
 * place is what stops those surfaces drifting out of alignment.
 *
 * `wide` exists for dense tables that need more room than the default; no page
 * opts into it yet.
 */
export function PageContainer({
  width = "default",
  as: Component = "div",
  className,
  ...props
}: PageContainerProps) {
  return (
    <Component
      className={cn("mx-auto w-full px-4 md:px-8", MAX_WIDTH[width], className)}
      {...props}
    />
  );
}
