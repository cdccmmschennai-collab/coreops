"use client";

import * as React from "react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Kpi } from "@/components/ui/kpi";

import { useMyPermissionBalance } from "../hooks";
import { PERMISSION_HISTORY_PATH, formatHours } from "../types";
import { PermissionRequestDialog } from "./permission-request-dialog";

/** The "Permission Remaining" attendance KPI: the month's figure, and the two
 *  actions that belong with it.
 *
 *      Permission Remaining
 *      4h
 *      [Request]  History
 *
 *  THE CARD ITSELF IS NOT A CONTROL. Only the two things in the action row do
 *  anything - Request opens the dialog, History opens this month's history, and
 *  clicking the label, the value or any empty space does nothing at all. An
 *  earlier version made the whole tile a click target, which meant the card
 *  looked like a button, stole the click from Request, and gave no hint about
 *  which of two destinations it would go to.
 *
 *  History is plain underlined text rather than a second button, so the tile still
 *  reads as a KPI with one primary action rather than a small control panel.
 *
 *  Not in Quick Actions, not on the Info page, not in navigation: the figure and
 *  its actions belong together, because the only thing an employee needs to know
 *  before asking is how many hours are left.
 *
 *  The month is the CURRENT Chennai business month, resolved by the server, so the
 *  tile does not roll over a day early for anyone reading it just after midnight
 *  IST. */
export function PermissionRemainingKpi() {
  const [open, setOpen] = React.useState(false);
  const balanceQuery = useMyPermissionBalance();
  const remaining = balanceQuery.data?.remaining_hours;

  return (
    <>
      <Kpi
        label="Permission Remaining"
        value={remaining === undefined ? "-" : formatHours(remaining)}
        action={
          <div className="flex items-center gap-3">
            <Button size="sm" variant="secondary" onClick={() => setOpen(true)}>
              Request
            </Button>
            {/* Secondary text action. A real link, so middle-click and
                open-in-new-tab work the way the rest of the app's links do. */}
            <Link
              href={PERMISSION_HISTORY_PATH}
              className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
            >
              History
            </Link>
          </div>
        }
      />

      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div
            className="absolute inset-0 bg-foreground/40"
            onClick={() => setOpen(false)}
            aria-hidden
          />
          <Card className="relative z-10 w-full max-w-md shadow-xl">
            <CardHeader className="border-b border-border px-5 py-3.5">
              <CardTitle className="text-base">Permission Request</CardTitle>
            </CardHeader>
            <CardContent className="pt-5">
              <PermissionRequestDialog onClose={() => setOpen(false)} />
            </CardContent>
          </Card>
        </div>
      )}
    </>
  );
}
