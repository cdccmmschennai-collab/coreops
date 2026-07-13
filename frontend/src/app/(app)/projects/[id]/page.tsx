"use client";

import { Suspense } from "react";
import { useParams } from "next/navigation";

import { ProjectDetail } from "@/features/projects/components/project-detail";

export default function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>();
  return (
    <Suspense>
      <ProjectDetail id={id} />
    </Suspense>
  );
}
