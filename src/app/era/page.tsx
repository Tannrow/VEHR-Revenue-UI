import Link from "next/link";

import { PageShell, SectionCard } from "@/components/page-shell";
import { fetchInternalJson } from "@/lib/internal-api";

import { EraUploadForm } from "./era-upload-form";

export const dynamic = "force-dynamic";

type HealthPayload = {
  ok?: boolean;
  proxiedPath?: string;
  backendUrl?: string | null;
  [key: string]: unknown;
};

async function getHealth(): Promise<{ payload: HealthPayload | null; error: string | null }> {
  try {
    return {
      payload: await fetchInternalJson<HealthPayload>("/api/health"),
      error: null,
    };
  } catch (error) {
    return {
      payload: null,
      error: error instanceof Error ? error.message : "Unable to load backend health.",
    };
  }
}

export default async function EraPage() {
  const { payload, error } = await getHealth();

  return (
    <PageShell
      title="ERA Intake"
      description="ERA uploads and backend health checks are routed through same-origin Next.js APIs."
      footer="ERA uploads post to /api/era and health checks read from /api/health."
    >
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <SectionCard title="Backend status">
          <div className="space-y-4 text-sm text-zinc-300">
            {error ? (
              <p className="rounded-md border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-amber-200">
                {error}
              </p>
            ) : (
              <pre className="overflow-x-auto rounded-lg border border-zinc-800 bg-black/50 p-4 text-xs text-zinc-200">
                {JSON.stringify(payload ?? { ok: false }, null, 2)}
              </pre>
            )}

            <Link
              href="/"
              className="inline-flex rounded-md border border-zinc-700 px-4 py-2 text-white transition hover:border-white"
            >
              Back to home
            </Link>
          </div>
        </SectionCard>

        <SectionCard title="ERA upload">
          <EraUploadForm />
        </SectionCard>
      </div>
    </PageShell>
  );
}
