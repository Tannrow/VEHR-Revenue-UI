import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function BillingPage() {
  return (
    <div className="space-y-4">
      <h1 className="text-3xl font-semibold tracking-tight text-slate-900">Billing</h1>
      <Card className="border-slate-200/70 shadow-sm">
        <CardHeader>
          <CardTitle className="text-base">Billing Workspace</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-slate-600">
          Placeholder for billing operations. Revenue-cycle logic is intentionally out of scope for Phase 1.
        </CardContent>
      </Card>
    </div>
  );
}
