import { RotateCw, ShieldCheck } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PreviewBanner } from "@/features/attendance/components/preview-banner";

export function SsoPreview() {
  return (
    <div>
      <PreviewBanner>SSO / SAML integration is not built yet. Configuration shown is sample data.</PreviewBanner>
      <Card className="max-w-xl">
        <CardContent className="p-5">
          <div className="mb-5 flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-secondary">
              <ShieldCheck className="h-4 w-4 text-muted-foreground" />
            </div>
            <div className="flex-1">
              <div className="font-medium">SAML SSO</div>
              <div className="text-xs text-muted-foreground">Connected to Okta · acme.okta.com</div>
            </div>
            <Badge variant="success">active</Badge>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>SSO domain</Label>
              <Input value="coreops.app" readOnly />
            </div>
            <div className="space-y-1.5">
              <Label>ACS URL</Label>
              <Input value="https://coreops.app/sso/saml/acs" readOnly className="font-mono text-xs" />
            </div>
          </div>
          <div className="mt-4 flex gap-2">
            <Button variant="secondary" disabled>
              <RotateCw className="h-4 w-4" />
              Re-sync
            </Button>
            <Button variant="ghost" disabled>View metadata</Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
