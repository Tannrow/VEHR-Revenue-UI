import Link from "next/link";

import { PageShell, SectionCard } from "@/components/page-shell";
import { fetchInternalJson } from "@/lib/internal-api";

export const dynamic = "force-dynamic";

type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };
type JsonRecord = { [key: string]: JsonValue };

function isRecord(value: JsonValue): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function getClaims(payload: JsonValue): JsonRecord[] {
  if (Array.isArray(payload)) {
    return payload.filter(isRecord);
  }

  if (!isRecord(payload)) {
    return [];
  }

  const collectionCandidate = ["claims", "items", "results", "data"]
    .map((key) => payload[key])
    .find(Array.isArray);

  return collectionCandidate ? collectionCandidate.filter(isRecord) : [];
}

async function getClaimsData(): Promise<{ payload: JsonValue | null; error: string | null }> {
  try {
    return {
      payload: await fetchInternalJson<JsonValue>("/api/claims"),
      error: null,
    };
  } catch (error) {
    return {
      payload: null,
      error: error instanceof Error ? error.message : "Unable to load claims data.",
    };
  }
}

function renderCellValue(value: JsonValue): string {
  if (Array.isArray(value) || isRecord(value)) {
    return JSON.stringify(value);
  }

  return value === null ? "null" : String(value);
}

export default async function ClaimsPage() {
  const { payload, error } = await getClaimsData();
  const claims = payload ? getClaims(payload) : [];
  const columns = Array.from(new Set(claims.flatMap((claim) => Object.keys(claim)))).slice(0, 5);

  return (
    <PageShell
      title="Claims"
      description="Claims are loaded through the UI's same-origin proxy route."
      footer="Claims data is served from /api/claims via the UI origin."
    >
      <SectionCard title="Claims workspace">
        <div className="space-y-6 text-sm text-zinc-300">
          {error ? (
            <p className="rounded-md border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-amber-200">
              {error}
            </p>
          ) : null}

          {claims.length > 0 && columns.length > 0 ? (
            <div className="overflow-x-auto rounded-lg border border-zinc-800">
              <table className="min-w-full divide-y divide-zinc-800 text-left">
                <thead className="bg-black/40 text-xs uppercase tracking-wide text-zinc-500">
                  <tr>
                    {columns.map((column) => (
                      <th key={column} className="px-4 py-3 font-medium">
                        {column}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800 bg-zinc-950/40">
                  {claims.slice(0, 10).map((claim, index) => (
                    <tr key={String(claim.claim_id ?? claim.id ?? index)}>
                      {columns.map((column) => (
                        <td key={column} className="px-4 py-3 align-top text-zinc-200">
                          {renderCellValue(claim[column])}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
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
