import type { ComponentType } from "react";
import Link from "next/link";
import { FolderOpen, Package } from "lucide-react";

import { RequireCapability } from "@/components/auth/require-capability";
import { PageHeader } from "@/components/shell/page-header";
import { Card, CardContent } from "@/components/ui/card";

function HubCard({
  href,
  icon: Icon,
  title,
  description,
}: {
  href: string;
  icon: ComponentType<{ className?: string }>;
  title: string;
  description: string;
}) {
  return (
    <Link href={href} className="block group">
      <Card className="h-full transition-shadow group-hover:shadow-md group-hover:border-primary/50">
        <CardContent className="flex flex-col items-start gap-3 p-6">
          <div className="rounded-lg bg-primary/10 p-3 text-primary">
            <Icon className="h-6 w-6" />
          </div>
          <div>
            <p className="font-semibold text-base">{title}</p>
            <p className="text-sm text-muted-foreground mt-0.5">{description}</p>
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}

export default function ProjectsHubPage() {
  return (
    <RequireCapability capability="project.view">
      <PageHeader title="Projects" />
      <div className="grid gap-4 sm:grid-cols-2 max-w-xl">
        <HubCard
          href="/projects/list"
          icon={FolderOpen}
          title="Projects"
          description="Browse and manage all projects"
        />
        <HubCard
          href="/projects/deliverables"
          icon={Package}
          title="Deliverables"
          description="View deliverables across all projects"
        />
      </div>
    </RequireCapability>
  );
}
