"use client";

import { useParams } from "next/navigation";

import { LeaveDetail } from "@/features/leave/components/leave-detail";

export default function LeaveDetailPage() {
  const { id } = useParams<{ id: string }>();
  return <LeaveDetail id={id} />;
}
