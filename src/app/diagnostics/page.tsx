import Link from "next/link";

import { PageShell, SectionCard } from "@/components/page-shell";
import { SignInRequiredCard } from "@/components/sign-in-required-card";
import { getAccessToken } from "@/lib/auth";

import { DiagnosticsPanel } from "./diagnostics-panel";

export const dynamic = "force-dynamic";

export default async function DiagnosticsPage() {
  const accessToken = await getAccessToken();

  if (!accessToken) {
    return (
      <PageShell
        title="Environment Diagnostics"
        description="Live MCP connector health for Azure, Postgres, and GitHub through the UI's same-origin proxy routes."
        footer="Diagnostics use /api/health, /api/auth/me, and /api/mcp-health via the UI origin."
      >
        <SignInRequiredCard resource="diagnostics" />
      </PageShell>
    );
  }

  return (
    <PageShell
      title="Environment Diagnostics"
      description="Live MCP connector health for Azure, Postgres, and GitHub through the UI's same-origin proxy routes."
      footer="Diagnostics use /api/health, /api/auth/me, and /api/mcp-health via the UI origin."
    >
      <SectionCard title="Connector health">
        <DiagnosticsPanel />
      </SectionCard>

      <div>
        <Link
          href="/"
          className="inline-flex rounded-md border border-zinc-700 px-4 py-2 text-white transition hover:border-white"
        >
          Back to home
        </Link>
      </div>
    </PageShell>
  );
}
