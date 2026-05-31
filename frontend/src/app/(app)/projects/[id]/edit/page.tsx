"use client";

import { useParams } from "next/navigation";

import { RequireCapability } from "@/components/auth/require-capability";
import { ProjectEdit } from "@/features/projects/components/project-edit";

export default function EditProjectPage() {
  const { id } = useParams<{ id: string }>();
  return (
    <RequireCapability capability="project.manage">
      <ProjectEdit id={id} />
    </RequireCapability>
  );
}
