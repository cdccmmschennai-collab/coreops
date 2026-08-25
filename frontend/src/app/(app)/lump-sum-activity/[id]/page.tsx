"use client";

import { useParams } from "next/navigation";

import { ContinuationDetail } from "@/features/continuation-requests/components/continuation-detail";

export default function ContinuationDetailPage() {
  const { id } = useParams<{ id: string }>();
  return <ContinuationDetail id={id} />;
}
