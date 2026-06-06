import { Card } from "@/components/ui/card";
import { PreviewBanner } from "@/features/attendance/components/preview-banner";

export function LeaveApprovalsPreview() {
  return (
    <div>
      <PreviewBanner>
        the Leave module is not built yet. Pending requests will appear here once it ships.
      </PreviewBanner>
      <Card className="p-8 text-center text-sm text-muted-foreground">
        No pending leave requests.
      </Card>
    </div>
  );
}
