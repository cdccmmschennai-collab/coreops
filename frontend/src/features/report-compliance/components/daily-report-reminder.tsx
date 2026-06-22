"use client";

import * as React from "react";
import { useRouter } from "next/navigation";

import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { nowInIST } from "@/lib/ist";

import { useMyCompliance } from "../hooks";

// Reminder fires at/after 17:15 local time.
const REMIND_HOUR = 17;
const REMIND_MINUTE = 15;
// "Remind Me Later" snoozes for 30 minutes (kept in-memory for the session).
const SNOOZE_MS = 30 * 60_000;

function pastReminderTime(now: Date): boolean {
  const minutes = now.getHours() * 60 + now.getMinutes();
  return minutes >= REMIND_HOUR * 60 + REMIND_MINUTE;
}

/**
 * 5:15 PM reminder: once it's past 17:15 and the employee has attendance today
 * but hasn't submitted today's report, prompt them. "Remind Me Later" snoozes
 * for 30 minutes; the prompt also self-dismisses the moment a report is
 * submitted (the compliance query refetches on focus / interval).
 */
export function DailyReportReminder() {
  const { data } = useMyCompliance();
  const router = useRouter();
  const [open, setOpen] = React.useState(false);
  const snoozedUntil = React.useRef(0);
  const [now, setNow] = React.useState(() => nowInIST());

  // Re-evaluate every minute so the reminder appears when 17:15 IST passes while
  // the app is already open (not only on the next data refetch).
  React.useEffect(() => {
    const id = window.setInterval(() => setNow(nowInIST()), 60_000);
    return () => window.clearInterval(id);
  }, []);

  const pending =
    !!data && data.has_attendance_today && !data.has_report_today;
  const due = pending && pastReminderTime(now);

  React.useEffect(() => {
    if (!pending) {
      setOpen(false); // report submitted (or no attendance) — clear any prompt
      return;
    }
    if (due && Date.now() >= snoozedUntil.current) {
      setOpen(true);
    }
  }, [pending, due]);

  function remindLater() {
    snoozedUntil.current = Date.now() + SNOOZE_MS;
    setOpen(false);
  }

  function submit() {
    setOpen(false);
    router.push("/work-reports/new");
  }

  return (
    <AlertDialog open={open} onOpenChange={(o) => !o && remindLater()}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Daily report pending</AlertDialogTitle>
          <AlertDialogDescription>
            Please submit today&apos;s work report.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <Button variant="secondary" onClick={remindLater}>
            Remind Me Later
          </Button>
          <Button onClick={submit}>Submit Report</Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
