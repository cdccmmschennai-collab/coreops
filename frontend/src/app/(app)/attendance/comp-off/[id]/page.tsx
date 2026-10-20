"use client";

import { useParams } from "next/navigation";

import { CompOffDetail } from "@/features/comp-off/components/comp-off-detail";

/** A comp off request's detail page - a child of the Attendance page, exactly
 *  as `/attendance/leave/[id]` is. There is no Comp Off list page: the list is
 *  the Attendance page's Comp Off tab. */
export default function CompOffDetailPage() {
  const { id } = useParams<{ id: string }>();
  return <CompOffDetail id={id} />;
}
