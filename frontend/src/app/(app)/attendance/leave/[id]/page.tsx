"use client";

import { Suspense } from "react";
import { useParams } from "next/navigation";

import { LeaveDetail } from "@/features/leave/components/leave-detail";

export default function LeaveDetailPage() {
  const { id } = useParams<{ id: string }>();
  // LeaveDetail reads the `from` parameter (which Leave list opened it) with
  // useSearchParams, which requires this boundary - the same wrapper
  // /attendance/page.tsx already uses for the very same reason.
  return (
    <Suspense>
      <LeaveDetail id={id} />
    </Suspense>
  );
}
