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
        title="Dashboard"
        description="Live revenue snapshot data is loaded through the UI's same-origin proxy route."
        footer={<span>Dashboard data is served from /api/dashboard via the UI origin. <a href="/diagnostics" className="underline hover:text-white">Open diagnostics</a>.</span>}
      >
        <SignInRequiredCard resource="the dashboard" />
      </PageShell>
    );
  }

  return (
    <PageShell
      title="Dashboard"
      description="Live revenue snapshot data is loaded through the UI's same-origin proxy route."
      footer={<span>Dashboard data is served from /api/dashboard via the UI origin. <a href="/diagnostics" className="underline hover:text-white">Open diagnostics</a>.</span>}
    >
      <DashboardContent />
    </PageShell>
  );
}
