import { PageShell } from "@/components/page-shell";
import { SignInRequiredCard } from "@/components/sign-in-required-card";
import { getAccessToken } from "@/lib/auth";

import { DashboardContent } from "./dashboard-content";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  const accessToken = await getAccessToken();

  if (!accessToken) {
    return (
      <PageShell
        eyebrow="Workflow-first command center"
        title="Work Queue"
        description="Start from a live work queue, not a passive dashboard. Every item is designed to answer what the user should do next."
        footer={<span>Queue-driven operating model with sidecar AI, object drill-down, and command-first actions. <a href="/diagnostics" className="underline hover:text-white">Open diagnostics</a>.</span>}
      >
        <SignInRequiredCard resource="the dashboard" />
      </PageShell>
    );
  }

  return (
    <PageShell
      eyebrow="Workflow-first command center"
      title="Work Queue"
      description="Triage denials, inspect the claim object model in-place, and use the AI sidecar to explain, recommend, and draft evidence-backed next steps."
      footer={<span>Queue-driven operating model with sidecar AI, object drill-down, and command-first actions. <a href="/diagnostics" className="underline hover:text-white">Open diagnostics</a>.</span>}
    >
      <DashboardContent />
    </PageShell>
  );
}
