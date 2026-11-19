"use client";

import { useParams } from "next/navigation";

import { RequireCapability } from "@/components/auth/require-capability";
import { ReworkApprovalDetail } from "@/features/rework-approvals/components/rework-approval-detail";

export default function ReworkApprovalDetailPage() {
  const { id } = useParams<{ id: string }>();
  // The page the PM's email links to. The capability gate is only the UI;
  // the backend authorizes every read and decision itself.
  return (
    <RequireCapability capability="activity.review">
      <ReworkApprovalDetail id={id} />
    </RequireCapability>
  );
}