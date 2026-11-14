"use client";

import { Suspense } from "react";
import { useParams } from "next/navigation";

import { RequireCapability } from "@/components/auth/require-capability";
import { DeliverableDetail } from "@/features/project-deliverables/components/deliverable-detail";

export default function DeliverableDetailPage() {
  const { id } = useParams<{ id: string }>();
  return (
    <RequireCapability capability="project.view">
      {/* useSearchParams (the `?from=` back link) needs a Suspense boundary. */}
      <Suspense>
        <DeliverableDetail id={id} />
      </Suspense>
    </RequireCapability>
  );
}
