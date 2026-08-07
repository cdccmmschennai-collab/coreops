"use client";

import { useParams } from "next/navigation";

import { ProjectEdit } from "@/features/projects/components/project-edit";

/**
 * No RequireCapability here: editing is no longer a role-only capability. A
 * project Head may edit the project they Head, which cannot be decided until
 * the project row is loaded — so ProjectEdit itself performs the project-aware
 * guard (and the API enforces it regardless).
 */
export default function EditProjectPage() {
  const { id } = useParams<{ id: string }>();
  return <ProjectEdit id={id} />;
}
