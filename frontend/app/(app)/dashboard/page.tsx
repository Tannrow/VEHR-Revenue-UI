"use client";

import { useEffect, useMemo, useState } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import MetricCard from "../_components/MetricCard";
import { apiFetch } from "@/lib/api";

type ClientRecord = {
  id: string;
};

type TaskPriority = "High" | "Medium" | "Low";

type OperationTask = {
  id: string;
  title: string;
  owner: string;
  due: string;
  priority: TaskPriority;
  overdue?: boolean;
};

type ActivityItem = {
  id: string;
  text: string;
  time: string;
};

const taskQueue: OperationTask[] = [
  {
    id: "task-1",
    title: "Follow up on incomplete intake packet",
    owner: "Admissions",
    due: "Today 10:30 AM",
    priority: "High",
  },
  {
    id: "task-2",
    title: "Confirm insurance information for pending referral",
    owner: "Care Coordination",
    due: "Today 1:00 PM",
    priority: "Medium",
  },
  {
    id: "task-3",
    title: "Return outreach call to family contact",
    owner: "Client Services",
    due: "Today 3:15 PM",
    priority: "Low",
  },
  {
    id: "task-4",
    title: "Escalate unsigned consent follow-up",
    owner: "Compliance",
    due: "Yesterday 4:00 PM",
    priority: "High",
    overdue: true,
  },
  {
    id: "task-5",
    title: "Second follow-up on no-show consultation",
    owner: "Intake",
    due: "Yesterday 2:30 PM",
    priority: "Medium",
    overdue: true,
  },
];

const recentActivity: ActivityItem[] = [
  { id: "a1", text: "Referral moved to Intake Scheduled", time: "9:12 AM" },
  { id: "a2", text: "Client profile updated with contact preference", time: "8:45 AM" },
  { id: "a3", text: "Document policy acknowledgement completed", time: "Yesterday" },
  { id: "a4", text: "Follow-up task reassigned to Admissions", time: "Yesterday" },
];

function taskPriorityClass(priority: TaskPriority): string {
  if (priority === "High") return "ui-status-error";
  if (priority === "Medium") return "ui-status-warning";
  return "ui-status-info";
}

export default function DashboardPage() {
  const [activeClients, setActiveClients] = useState<number>(0);

  useEffect(() => {
    let isMounted = true;

    async function loadClientCount() {
      try {
        const data = await apiFetch<ClientRecord[]>("/api/v1/patients", { cache: "no-store" });
        if (!isMounted) return;
        setActiveClients(data.length);
      } catch {
        if (!isMounted) return;
        setActiveClients(0);
      }
    }

    void loadClientCount();
    return () => {
      isMounted = false;
    };
  }, []);

  const tasksDueToday = useMemo(
    () => taskQueue.filter((task) => !task.overdue).length,
    [],
  );
  const overdueFollowUps = useMemo(
    () => taskQueue.filter((task) => task.overdue).length,
    [],
  );
  const openReferrals = 12;

  return (
    <div className="flex flex-col gap-6">
      <div className="space-y-3">
        <p className="text-[11px] font-semibold uppercase tracking-[0.32em] text-slate-400">
          {"Encompass 360"}
        </p>
        <h1 className="text-[2rem] font-semibold tracking-tight text-slate-900">Operations</h1>
        <p className="text-sm text-slate-500">
          Focused CRM operations view for daily execution.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Tasks due today" value={`${tasksDueToday}`} hint="Action queue" />
        <MetricCard label="Overdue follow-ups" value={`${overdueFollowUps}`} hint="Needs immediate attention" />
        <MetricCard label="Active clients" value={`${activeClients}`} hint="Current relationship records" />
        <MetricCard label="Open referrals" value={`${openReferrals}`} hint="Prospects in pipeline" />
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.7fr_1fr]">
        <Card className="bg-white shadow-sm">
          <CardHeader className="pb-3">
            <CardTitle className="text-lg text-slate-900">Task List</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 pt-0">
            {taskQueue.map((task) => (
              <div key={task.id} className="rounded-lg bg-slate-50 px-4 py-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-sm font-semibold text-slate-900">{task.title}</p>
                  <span className={`rounded-md border px-2 py-0.5 text-[11px] font-semibold ${taskPriorityClass(task.priority)}`}>
                    {task.priority}
                  </span>
                </div>
                <div className="mt-1 flex flex-wrap gap-3 text-xs text-slate-500">
                  <span>Owner: {task.owner}</span>
                  <span>Due: {task.due}</span>
                  {task.overdue ? <span className="text-[var(--ui-status-error)]">Overdue</span> : null}
                </div>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card className="bg-white shadow-sm">
          <CardHeader className="pb-3">
            <CardTitle className="text-lg text-slate-900">Recent Activity</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 pt-0">
            {recentActivity.map((activity) => (
              <div key={activity.id} className="rounded-lg bg-slate-50 px-3 py-2">
                <p className="text-sm text-slate-700">{activity.text}</p>
                <p className="mt-1 text-xs text-slate-500">{activity.time}</p>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
