"use client";

import { useParams } from "next/navigation";

import { ProjectDetail } from "@/features/projects/components/project-detail";

export default function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>();
  return <ProjectDetail id={id} />;
}
