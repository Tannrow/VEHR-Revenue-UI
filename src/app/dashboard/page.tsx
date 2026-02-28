import { getPublicBackendUrl, probeBackendHealth } from "@/lib/backend";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  const publicUrl = getPublicBackendUrl();
  const health = await probeBackendHealth();

  // Show only the path component of the tested endpoint to avoid leaking
  // internal hostnames (e.g. from BACKEND_INTERNAL_URL).
  let endpointDisplay: string | null = null;
  if (health.endpointTried) {
    try {
      endpointDisplay = new URL(health.endpointTried).pathname;
    } catch {
      endpointDisplay = health.endpointTried;
    }
  }

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
              <dd className="font-mono break-all">{publicUrl ?? "Not configured"}</dd>
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
              <dd className="font-mono break-all">{endpointDisplay ?? "None"}</dd>
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
