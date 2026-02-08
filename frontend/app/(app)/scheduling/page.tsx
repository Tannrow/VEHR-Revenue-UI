import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function SchedulingPage() {
  return (
    <div className="space-y-4">
      <h1 className="text-3xl font-semibold tracking-tight text-slate-900">Scheduling</h1>
      <Card className="border-slate-200/70 shadow-sm">
        <CardHeader>
          <CardTitle className="text-base">Scheduling Console</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-slate-600">
          Placeholder for appointment calendars, staffing assignments, and service-level care plans.
        </CardContent>
      </Card>
    </div>
  );
}
