"use client";

import * as React from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Kpi } from "@/components/ui/kpi";

import { useMyPermissionBalance } from "../hooks";
import { formatHours } from "../types";
import { PermissionRequestDialog } from "./permission-request-dialog";

/** The "Permission Remaining" attendance KPI: the month's figure, and the one
 *  action that belongs with it.
 *
 *      Permission Remaining
 *      4h                    [Request]
 *
 *  THE CARD ITSELF IS NOT A CONTROL. Only Request does anything - clicking the
 *  label, the value or any empty space does nothing at all. An earlier version
 *  made the whole tile a click target, which meant the card looked like a
 *  button and stole the click from Request.
 *
 *  History lives inside the Request dialog, not on this tile - see
 *  PermissionRequestDialog.
 *
 *  Not in Quick Actions, not on the Info page, not in navigation: the figure and
 *  its action belong together, because the only thing an employee needs to know
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
          <Button size="sm" variant="secondary" onClick={() => setOpen(true)}>
            Request
          </Button>
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
