"use client";

import * as React from "react";
import { BookOpen } from "lucide-react";

import { Button, type ButtonProps } from "@/components/ui/button";

import { BenchmarkGuideDialog } from "./benchmark-guide-dialog";

/**
 * The single, shared Benchmark Guide entry point. Both places that surface the
 * guide — the dashboard shortcut and the Reports page (beside New Report) —
 * render THIS component, so they always open the exact same dialog.
 *
 * Defaults to the `secondary` variant so it never competes with the primary
 * "New report" action beside it.
 */
export function BenchmarkGuideButton({
  variant = "secondary",
  className,
  children,
  ...props
}: Omit<ButtonProps, "onClick" | "asChild">) {
  const [open, setOpen] = React.useState(false);
  return (
    <>
      <Button variant={variant} className={className} onClick={() => setOpen(true)} {...props}>
        <BookOpen className="h-4 w-4" />
        {children ?? "Benchmark Guide"}
      </Button>
      <BenchmarkGuideDialog open={open} onOpenChange={setOpen} />
    </>
  );
}
