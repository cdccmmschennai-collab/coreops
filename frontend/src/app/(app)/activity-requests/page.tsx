import { RequireCapability } from "@/components/auth/require-capability";
import { ActivityRequestsView } from "@/features/activity-requests/components/activity-requests-view";

export default function ActivityRequestsPage() {
  return (
    <RequireCapability capability="activity.review">
      <ActivityRequestsView />
    </RequireCapability>
  );
}
