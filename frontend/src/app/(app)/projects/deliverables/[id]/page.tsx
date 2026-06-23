"use client";

import { useParams } from "next/navigation";

import { RequireCapability } from "@/components/auth/require-capability";
import { DeliverableDetail } from "@/features/project-deliverables/components/deliverable-detail";

export default function DeliverableDetailPage() {
  const { id } = useParams<{ id: string }>();
  return (
    <RequireCapability capability="project.view">
      <DeliverableDetail id={id} />
    </RequireCapability>
  );
}
