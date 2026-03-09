import Link from "next/link";

import { PageShell, SectionCard } from "@/components/page-shell";
import { fetchInternalJson } from "@/lib/internal-api";

export const dynamic = "force-dynamic";

type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };

function isRecord(value: JsonValue): value is { [key: string]: JsonValue } {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function getMetricEntries(payload: JsonValue): Array<[string, string]> {
  if (!isRecord(payload)) {
    return [];
  }

  return Object.entries(payload)
    .filter(([, value]) => ["string", "number", "boolean"].includes(typeof value) || value === null)
    .slice(0, 6)
    .map(([key, value]) => [key, value === null ? "null" : String(value)]);
}

async function getDashboardData(): Promise<{ payload: JsonValue | null; error: string | null }> {
  try {
    return {
      payload: await fetchInternalJson<JsonValue>("/api/dashboard"),
      error: null,
    };
  } catch (error) {
    return {
      payload: null,
      error: error instanceof Error ? error.message : "Unable to load dashboard data.",
    };
  }
}

export default async function DashboardPage() {
  const { payload, error } = await getDashboardData();
  const metrics = payload ? getMetricEntries(payload) : [];

  return (
    <PageShell
      title="Dashboard"
      description="Live dashboard data is loaded through the same-origin Next.js proxy."
      footer="Dashboard data is served from /api/dashboard via the UI origin."
    >
      <SectionCard title="Revenue dashboard">
        <div className="space-y-6 text-sm text-zinc-300">
          {error ? (
            <p className="rounded-md border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-amber-200">
              {error}
            </p>
          ) : null}

          {metrics.length > 0 ? (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
              {metrics.map(([key, value]) => (
                <div key={key} className="rounded-lg border border-zinc-800 bg-black/40 p-4">
                  <p className="text-xs uppercase tracking-wide text-zinc-500">{key}</p>
                  <p className="mt-2 text-2xl font-semibold text-white">{value}</p>
                </div>
              ))}
            </div>
          ) : null}

          <div className="space-y-3">
            <p className="text-zinc-400">Backend response</p>
            <pre className="overflow-x-auto rounded-lg border border-zinc-800 bg-black/50 p-4 text-xs text-zinc-200">
              {JSON.stringify(payload ?? { error: error ?? "No data returned." }, null, 2)}
            </pre>
          </div>

          <Link
            href="/"
            className="inline-flex rounded-md border border-zinc-700 px-4 py-2 text-white transition hover:border-white"
          >
            Back to home
          </Link>
        </div>
      </SectionCard>
    </PageShell>
  );
}
