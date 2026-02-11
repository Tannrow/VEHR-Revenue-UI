"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const tasks = [
  { id: "t1", title: "Call referred prospect for intake scheduling", due: "Today 9:30 AM", owner: "Admissions" },
  { id: "t2", title: "Send document checklist to active client", due: "Today 11:00 AM", owner: "Client Services" },
  { id: "t3", title: "Review overdue follow-up notes", due: "Today 2:00 PM", owner: "Operations" },
  { id: "t4", title: "Escalate stalled referral after 48 hours", due: "Overdue", owner: "Intake" },
];

export default function TasksPage() {
  return (
    <div className="flex flex-col gap-6">
      <div className="space-y-3">
        <p className="text-[11px] font-semibold uppercase tracking-[0.32em] text-slate-400">Encompass 360</p>
        <h1 className="text-[2rem] font-semibold tracking-tight text-slate-900">Tasks</h1>
        <p className="text-sm text-slate-500">Prioritized task queue for daily CRM operations.</p>
      </div>

      <Card className="bg-white shadow-sm">
        <CardHeader className="pb-3">
          <CardTitle className="text-lg text-slate-900">Action Queue</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 pt-0">
          {tasks.map((task) => (
            <div key={task.id} className="rounded-lg bg-slate-50 px-4 py-3">
              <p className="text-sm font-semibold text-slate-900">{task.title}</p>
              <div className="mt-1 flex flex-wrap gap-3 text-xs text-slate-500">
                <span>Owner: {task.owner}</span>
                <span>Due: {task.due}</span>
              </div>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
