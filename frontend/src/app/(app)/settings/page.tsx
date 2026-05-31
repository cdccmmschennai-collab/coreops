import { Suspense } from "react";

import { RequireCapability } from "@/components/auth/require-capability";
import { UsersView } from "@/features/users/components/users-view";

export default function SettingsPage() {
  return (
    <RequireCapability capability="user.manage">
      <Suspense>
        <UsersView />
      </Suspense>
    </RequireCapability>
  );
}
