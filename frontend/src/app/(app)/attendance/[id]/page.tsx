"use client";

import { useParams } from "next/navigation";

import { AttendanceDetail } from "@/features/attendance/components/attendance-detail";

export default function AttendanceDetailPage() {
  const { id } = useParams<{ id: string }>();
  return <AttendanceDetail id={id} />;
}
