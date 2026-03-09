import { probeBackendHealth } from "@/lib/backend";
import { getBackendRuntimeConfig } from "@/lib/env";
import { PageShell, SectionCard } from "@/components/page-shell";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  const runtimeConfig = getBackendRuntimeConfig();
  const backendUrl = runtimeConfig.baseUrl;
  const health = await probeBackendHealth().catch((error) => ({
    connected: false,
    endpointTried: null,
    details:
      error instanceof Error
        ? `Backend health probe failed: ${error.message}`
        : "Backend health probe failed. Rendering staging fallback UI.",
    configuredBaseUrl: backendUrl,
    source: runtimeConfig.source,
  }));

  return (
    <PageShell
      title="Executive Dashboard"
      description="Revenue OS dashboard is connected through environment-based backend wiring."
      footer="Staging UI · This route renders even when backend connectivity is unavailable."
    >
      <SectionCard title="Backend Connectivity">
        <dl className="space-y-2 text-sm">
          <div>
            <dt className="text-zinc-400">Configured backend URL</dt>
            <dd className="font-mono break-all">{backendUrl ?? "Not configured"}</dd>
          </div>
          <div>
            <dt className="text-zinc-400">Configuration source</dt>
            <dd className="capitalize">{health.source}</dd>
          </div>
          <div>
            <dt className="text-zinc-400">Runtime mode</dt>
            <dd>Dynamic server render (no build-time probe)</dd>
          </div>
          <div>
            <dt className="text-zinc-400">Status</dt>
            <dd className={health.connected ? "text-emerald-400" : "text-amber-400"}>
              {health.connected ? "Connected" : "Not connected"}
            </dd>
          </div>
          <div>
            <dt className="text-zinc-400">Endpoint tested</dt>
            <dd className="font-mono break-all">{health.endpointTried ?? "None"}</dd>
          </div>
          <div>
            <dt className="text-zinc-400">Health API route</dt>
            <dd className="font-mono break-all">/api/health</dd>
          </div>
          <div>
            <dt className="text-zinc-400">Details</dt>
            <dd>{health.details}</dd>
          </div>
        </dl>
      </SectionCard>
    </PageShell>
  );
}
