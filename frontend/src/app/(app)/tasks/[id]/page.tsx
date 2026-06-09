import { TaskDetail } from "@/features/tasks/components/task-detail";

export default function TaskDetailPage({ params }: { params: { id: string } }) {
  return <TaskDetail id={params.id} />;
}
