"use client";

import * as React from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Kpi } from "@/components/ui/kpi";

import { shortMonthLabel } from "@/features/attendance/selected-month";

import { useMyPermissionBalance } from "../hooks";
import { PERMISSION_HISTORY_PATH, formatHours } from "../types";
import { PermissionRequestDialog } from "./permission-request-dialog";

interface Props {
  /** The month the tile reports, as `YYYY-MM-01`. Omitted asks the server for
   *  the current Chennai business month. */
  month?: string;
  /** Whether that month is the one running now. Only used to word the tile; the
   *  server's `requests_allowed` is what actually decides the action. */
  isCurrentMonth?: boolean;
}

/** The "Permission Remaining" attendance KPI: the month's figure, and the one
 *  action that belongs with it.
 *
 *      Permission Remaining
 *      4h                    [Request]
 *
 *  THE CARD ITSELF IS NOT A CONTROL. Only the button does anything - clicking the
 *  label, the value or any empty space does nothing at all. An earlier version
 *  made the whole tile a click target, which meant the card looked like a
 *  button and stole the click from Request.
 *
 *  THE ALLOWANCE DOES NOT CARRY FORWARD. Each month is summed on its own
 *  server-side - 4h minus that month's approved hours - so an unused August hour
 *  can never become a fifth September hour. This tile never adds months up; it
 *  shows the one figure the server derived for the month it was asked about.
 *
 *  A FINISHED MONTH CANNOT BE SPENT FROM. When the server says
 *  `requests_allowed: false`, Request is replaced by History rather than left as
 *  a button the backend would refuse. The figures stay exactly as they are and
 *  the history stays reachable - a closed month is read-only, never hidden.
 *
 *  The month is resolved server-side, so the tile does not roll over a day early
 *  for anyone reading it just after midnight IST. */
export function PermissionRemainingKpi({ month, isCurrentMonth = true }: Props) {
  const router = useRouter();
  const [open, setOpen] = React.useState(false);
  const balanceQuery = useMyPermissionBalance(month);
  const balance = balanceQuery.data;
  const remaining = balance?.remaining_hours;

  // Trust the server's flag; fall back to "this is the current month" only while
  // the balance is still loading, so the button does not flicker in and out.
  const requestsAllowed = balance ? balance.requests_allowed : isCurrentMonth;
  const monthLabel = month ? shortMonthLabel(month) : "";

  /** This month's own history page, opened on the month being read. */
  function openHistory() {
    router.push(month ? `${PERMISSION_HISTORY_PATH}?pm_month=${month}` : PERMISSION_HISTORY_PATH);
  }

  return (
    <>
      <Kpi
        // "Permission Remaining · Aug 2026" for a past month, in the SAME short
        // form the three tiles beside it use - it read "· August 2026" before,
        // which was the one label long enough to wrap onto a second line and
        // make this card taller than its neighbours.
        label={
          isCurrentMonth
            ? "Permission Remaining"
            : `Permission Remaining · ${monthLabel}`
        }
        value={remaining === undefined ? "-" : formatHours(remaining)}
        action={
          requestsAllowed ? (
            <Button size="sm" variant="secondary" onClick={() => setOpen(true)}>
              Request
            </Button>
          ) : (
            // History, not a disabled Request: the month still has something to
            // show, and offering a dead button would be worse than offering the
            // thing that does work. The button IS the explanation - a closed
            // month offers History and nothing else - so the
            // "Permission requests are closed for previous months." line that
            // used to sit under it said nothing the tile was not already
            // showing, and cost the card an extra line to say it.
            <Button size="sm" variant="secondary" onClick={openHistory}>
              History
            </Button>
          )
        }
        hint={
          balanceQuery.isError
            ? "Couldn't load this month's permission balance."
            : undefined
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
