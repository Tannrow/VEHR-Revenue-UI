import { getBackendBaseUrl, probeBackendHealth } from "@/lib/backend";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  const backendUrl = getBackendBaseUrl();
  const health = await probeBackendHealth();

  return (
    <main className="min-h-screen bg-black text-white p-12">
      <div className="max-w-6xl mx-auto space-y-6">
        <div>
          <h1 className="text-3xl font-bold mb-2">Executive Dashboard</h1>
          <p className="text-zinc-400">
            Revenue OS dashboard is connected through environment-based backend wiring.
          </p>
        </div>

        <section className="rounded-xl border border-zinc-800 bg-zinc-900 p-6">
          <h2 className="text-xl font-semibold mb-3">Backend Connectivity</h2>
          <dl className="space-y-2 text-sm">
            <div>
              <dt className="text-zinc-400">Configured backend URL</dt>
              <dd className="font-mono break-all">{backendUrl ?? "Not configured"}</dd>
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
              <dt className="text-zinc-400">Details</dt>
              <dd>{health.details}</dd>
            </div>
          </dl>
        </section>
      </div>
    </main>
  );
}
