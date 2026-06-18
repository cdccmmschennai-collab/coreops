"use client";

import * as React from "react";
import { CalendarDays, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { EmptyState } from "@/components/feedback/empty-state";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/features/auth/auth-provider";
import { can } from "@/lib/rbac";
import { cn } from "@/lib/utils";

import { useCalendarEvents, useCreateCalendarEvent, useDeleteCalendarEvent } from "../hooks";

/** Returns ISO strings for the current year (± 6 months window). */
function yearWindow() {
  const now = new Date();
  const from = new Date(now.getFullYear(), 0, 1);
  const to = new Date(now.getFullYear(), 11, 31);
  return {
    from: from.toISOString().slice(0, 10),
    to: to.toISOString().slice(0, 10),
  };
}

function formatEventDate(iso: string) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("en-IN", {
    weekday: "short",
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

export function HolidayManager() {
  const { role } = useAuth();
  const canManage = can(role, "calendar.manage");
  const { from, to } = yearWindow();

  const query = useCalendarEvents({ from, to, limit: 100 });
  const createMutation = useCreateCalendarEvent();
  const deleteMutation = useDeleteCalendarEvent();

  const [date, setDate] = React.useState("");
  const [title, setTitle] = React.useState("");
  const [adding, setAdding] = React.useState(false);

  const events = query.data?.items ?? [];
  const upcoming = events.filter((e) => e.event_date >= new Date().toISOString().slice(0, 10));
  const past = events.filter((e) => e.event_date < new Date().toISOString().slice(0, 10));

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    if (!date || !title.trim()) return;
    try {
      await createMutation.mutateAsync({
        event_date: date,
        title: title.trim(),
        event_type: "holiday",
      });
      toast.success("Holiday added");
      setDate("");
      setTitle("");
      setAdding(false);
    } catch {
      toast.error("Failed to add holiday");
    }
  }

  async function handleDelete(id: string, name: string) {
    try {
      await deleteMutation.mutateAsync(id);
      toast.success(`"${name}" removed`);
    } catch {
      toast.error("Failed to remove holiday");
    }
  }

  return (
    <div className="space-y-6">
      {canManage && (
        <Card>
          <CardHeader className="border-b border-border p-4">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">Add Holiday</CardTitle>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setAdding((v) => !v)}
              >
                <Plus className="h-4 w-4" />
                {adding ? "Cancel" : "New Holiday"}
              </Button>
            </div>
          </CardHeader>
          {adding && (
            <CardContent className="pt-4">
              <form onSubmit={(e) => void handleAdd(e)} className="flex flex-wrap gap-3">
                <Input
                  type="date"
                  value={date}
                  onChange={(e) => setDate(e.target.value)}
                  required
                  className="w-44"
                />
                <Input
                  placeholder="Holiday name (e.g. Pongal)"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  required
                  className="flex-1 min-w-48"
                />
                <Button type="submit" disabled={createMutation.isPending}>
                  Add
                </Button>
              </form>
            </CardContent>
          )}
        </Card>
      )}

      <Card>
        <CardHeader className="border-b border-border p-4">
          <CardTitle className="text-base flex items-center gap-2">
            <CalendarDays className="h-4 w-4 text-violet-600" />
            Upcoming Holidays - {new Date().getFullYear()}
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {query.isLoading ? (
            <div className="p-6 text-sm text-muted-foreground">Loading…</div>
          ) : upcoming.length === 0 ? (
            <EmptyState
              title="No upcoming holidays"
              description={
                canManage
                  ? "Add holidays above so the team knows when to plan time off."
                  : "No holidays have been scheduled yet."
              }
            />
          ) : (
            <ul className="divide-y divide-border">
              {upcoming.map((ev) => (
                <li
                  key={ev.id}
                  className="flex items-center justify-between px-4 py-3"
                >
                  <div>
                    <p className="font-medium text-sm">{ev.title}</p>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {formatEventDate(ev.event_date)}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="rounded-full bg-violet-50 px-2 py-0.5 text-[11px] font-medium text-violet-700">
                      Holiday
                    </span>
                    {canManage && (
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 text-muted-foreground hover:text-destructive"
                        onClick={() => void handleDelete(ev.id, ev.title)}
                        disabled={deleteMutation.isPending}
                        aria-label={`Remove ${ev.title}`}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {past.length > 0 && (
        <Card>
          <CardHeader className="border-b border-border p-4">
            <CardTitle className={cn("text-base text-muted-foreground")}>
              Past Holidays
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <ul className="divide-y divide-border">
              {past
                .slice()
                .reverse()
                .map((ev) => (
                  <li
                    key={ev.id}
                    className="flex items-center justify-between px-4 py-3 opacity-60"
                  >
                    <div>
                      <p className="font-medium text-sm">{ev.title}</p>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        {formatEventDate(ev.event_date)}
                      </p>
                    </div>
                    {canManage && (
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 text-muted-foreground hover:text-destructive"
                        onClick={() => void handleDelete(ev.id, ev.title)}
                        disabled={deleteMutation.isPending}
                        aria-label={`Remove ${ev.title}`}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    )}
                  </li>
                ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
