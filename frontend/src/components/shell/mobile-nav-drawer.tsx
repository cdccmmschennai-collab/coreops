"use client";

import * as React from "react";
import { usePathname } from "next/navigation";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { Menu, X } from "lucide-react";

import { Sidebar } from "@/components/shell/sidebar";
import { Button } from "@/components/ui/button";

/** Mirrors the Tailwind `md` screen; the drawer only exists below it. */
const DESKTOP_MEDIA_QUERY = "(min-width: 861px)";

/**
 * Off-canvas navigation below the md (861px) breakpoint. Radix owns the focus
 * trap, focus restoration, Escape, outside-click and body scroll lock; the two
 * behaviours added here are closing on a route change and closing at the
 * desktop breakpoint, neither of which the primitive can observe.
 */
export function MobileNavDrawer() {
  const [open, setOpen] = React.useState(false);
  const pathname = usePathname();
  const lastPathname = React.useRef(pathname);

  React.useEffect(() => {
    if (lastPathname.current === pathname) return;
    lastPathname.current = pathname;
    setOpen(false);
  }, [pathname]);

  // `md:hidden` only takes the panel out of view: without this the dialog would
  // stay open past the breakpoint and leave the body scroll-locked on desktop.
  React.useEffect(() => {
    if (!open) return;

    const query = window.matchMedia(DESKTOP_MEDIA_QUERY);
    if (query.matches) {
      setOpen(false);
      return;
    }

    function handleChange(event: MediaQueryListEvent) {
      if (event.matches) setOpen(false);
    }

    query.addEventListener("change", handleChange);
    return () => query.removeEventListener("change", handleChange);
  }, [open]);

  return (
    <DialogPrimitive.Root open={open} onOpenChange={setOpen}>
      <DialogPrimitive.Trigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="md:hidden"
          aria-label="Open navigation"
        >
          <Menu className="h-5 w-5" />
        </Button>
      </DialogPrimitive.Trigger>

      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-foreground/40 backdrop-blur-sm data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:animate-in data-[state=open]:fade-in-0 md:hidden" />
        <DialogPrimitive.Content
          aria-describedby={undefined}
          className="fixed left-0 top-0 z-50 flex h-full w-64 flex-col bg-background shadow-xl duration-200 data-[state=closed]:animate-out data-[state=closed]:slide-out-to-left data-[state=open]:animate-in data-[state=open]:slide-in-from-left motion-reduce:animate-none md:hidden"
        >
          <DialogPrimitive.Title className="sr-only">
            Main navigation
          </DialogPrimitive.Title>

          <DialogPrimitive.Close asChild>
            <Button
              variant="ghost"
              size="icon"
              className="absolute right-2 top-2 z-10 h-8 w-8"
              aria-label="Close navigation"
            >
              <X className="h-4 w-4" />
            </Button>
          </DialogPrimitive.Close>

          {/* Scrolling is confined to the nav so the close control stays put on
              short viewports (landscape phones). */}
          <div className="min-h-0 flex-1 overflow-y-auto">
            <Sidebar />
          </div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
