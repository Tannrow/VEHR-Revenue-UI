import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function AdministrationPage() {
  return (
    <div className="space-y-4">
      <h1 className="text-3xl font-semibold tracking-tight text-slate-900">Administration</h1>
      <Card className="border-slate-200/70 shadow-sm">
        <CardHeader>
          <CardTitle className="text-base">Organization Administration</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-slate-600">
          Placeholder for organization settings, user governance, and service catalog controls.
        </CardContent>
      </Card>
    </div>
  );
}
