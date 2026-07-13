import { Suspense } from "react";

import { NotificationList } from "@/features/notifications/components/notification-list";

export default function NotificationsPage() {
  return (
    <Suspense>
      <NotificationList />
    </Suspense>
  );
}
