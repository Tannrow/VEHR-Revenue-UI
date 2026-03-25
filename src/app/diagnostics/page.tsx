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
        description="Live connector and ERA AI runtime health through the UI's same-origin proxy routes."
        footer="Diagnostics use /api/health, /api/auth/me, /api/mcp-health, and /api/readyz/components via the UI origin."
      >
        <SignInRequiredCard resource="diagnostics" />
      </PageShell>
    );
  }

  return (
    <PageShell
      title="Environment Diagnostics"
      description="Live connector and ERA AI runtime health through the UI's same-origin proxy routes."
      footer="Diagnostics use /api/health, /api/auth/me, /api/mcp-health, and /api/readyz/components via the UI origin."
    >
      <SectionCard title="Connector health">
        <DiagnosticsPanel />
      </SectionCard>

      <SectionCard title="Operator runbook">
        <div className="space-y-4 text-sm text-zinc-300">
          <p>
            Use this page as the live source of truth, then follow the permanent MCP operator runbook in the VEHR repo
            when a connector flips red or staging behaves unexpectedly.
          </p>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="rounded-xl border border-zinc-800 bg-black/30 p-4">
              <p className="text-xs uppercase tracking-[0.18em] text-zinc-500">Runbook location</p>
              <p className="mt-2 break-all font-mono text-white">docs/mcp-operator-runbook.md</p>
              <a
                href="https://github.com/360E/VEHR/blob/main/docs/mcp-operator-runbook.md"
                target="_blank"
                rel="noreferrer"
                className="mt-4 inline-flex rounded-md border border-zinc-700 px-4 py-2 text-white transition hover:border-white"
              >
                Open runbook
              </a>
            </div>

            <div className="rounded-xl border border-zinc-800 bg-black/30 p-4">
              <p className="text-xs uppercase tracking-[0.18em] text-zinc-500">Healthy runtime contract</p>
              <ul className="mt-2 space-y-2 text-zinc-300">
                <li>Postgres: valid `DATABASE_URL` and network reachability.</li>
                <li>GitHub: `GITHUB_REPO` plus a credential that can read `360E/VEHR`.</li>
                <li>Azure: `AZURE_SUBSCRIPTION_ID`, `AZURE_CLIENT_ID`, and Reader access on staging resources.</li>
                <li>Document Intelligence: `AZURE_DOCINTEL_ENDPOINT` plus either key or managed identity auth.</li>
                <li>Azure OpenAI: endpoint, deployment, API version, and either key or managed identity auth.</li>
              </ul>
            </div>
          </div>
        </div>
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
