"use client";

import { useParams } from "next/navigation";

import { PermissionDetail } from "@/features/permissions/components/permission-detail";

export default function PermissionDetailPage() {
  const { id } = useParams<{ id: string }>();
  return <PermissionDetail id={id} />;
}
