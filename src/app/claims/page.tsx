import Link from "next/link";

import { PageShell, SectionCard } from "@/components/page-shell";
import { SignInRequiredCard } from "@/components/sign-in-required-card";
import { getAccessToken } from "@/lib/auth";
import { isFetchFailedMessage } from "@/lib/error-messages";
import { fetchInternal } from "@/lib/internal-api";
import { revenueQueue } from "@/lib/mock/revenue-os";

export const dynamic = "force-dynamic";

type ClaimRecord = {
  id?: string;
  external_claim_id?: string | null;
  patient_name?: string | null;
  payer_name?: string | null;
  status?: string | null;
  created_at?: string | null;
};

function isClaimRecord(value: unknown): value is ClaimRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function formatErrorMessage(status: number, payload: unknown, text: string): string {
  if (typeof payload === "string" && payload.trim()) {
    return isFetchFailedMessage(payload) ? "Unable to reach the VEHR claims endpoint right now." : payload.trim();
  }

  if (payload && typeof payload === "object" && !Array.isArray(payload)) {
    const detail = "detail" in payload ? payload.detail : null;
    const error = "error" in payload ? payload.error : null;
    if (typeof error === "string" && error.trim()) {
      return error.trim();
    }
    if (typeof detail === "string" && detail.trim()) {
      return detail.trim();
    }
  }

  if (text.trim()) {
    return text.trim();
  }

  return `Unable to load claims (status ${status}).`;
}

async function getClaimsState(): Promise<{ claims: ClaimRecord[]; error: string | null }> {
  try {
    const response = await fetchInternal("/api/claims");

    if (!response.ok) {
      return {
        claims: [],
        error: formatErrorMessage(response.status, response.data, response.text),
      };
    }

    const payload = Array.isArray(response.data) ? response.data.filter(isClaimRecord) : [];
    return {
      claims: payload,
      error: null,
    };
  } catch (error) {
    return {
      claims: [],
      error:
        error instanceof Error && !isFetchFailedMessage(error.message)
          ? error.message
          : "Unable to load claims right now.",
    };
  }
}

export default async function ClaimsPage() {
  const accessToken = await getAccessToken();

  if (!accessToken) {
    return (
      <PageShell
        eyebrow="Object-first revenue model"
        title="Claims"
        description="Claim, denial, encounter, patient, payer, authorization, documents, and timeline all stay connected so operators can act without navigating away."
        footer="Claims data is served from /api/claims via the UI origin."
      >
        <SignInRequiredCard resource="claims" />
      </PageShell>
    );
  }

  const { claims, error } = await getClaimsState();
  const exampleObjects = revenueQueue.slice(0, 3);

  return (
    <PageShell
      eyebrow="Object-first revenue model"
      title="Claims"
      description="This surface is designed like an operational object explorer: inspect the live claim inventory, keep context around related denials and documents, and move directly into action."
      footer="Claims data is served from /api/claims via the UI origin."
    >
      <div className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
        <SectionCard title="Live claim inventory" subtitle="Real backend claims stay visible here; the surrounding UX mirrors the object workflow model used across Revenue OS.">
          <div className="space-y-4">
            {error ? (
              <div className="rounded-2xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
                {error}
              </div>
            ) : null}

            {!error && claims.length === 0 ? (
              <div className="rounded-2xl border border-white/8 bg-black/20 px-4 py-4 text-sm text-slate-300">
                No live claims were returned, so the workflow examples on this page show the intended claim object architecture.
              </div>
            ) : null}

            {claims.length > 0 ? (
              <div className="overflow-hidden rounded-[22px] border border-white/8">
                <table className="min-w-full text-left text-sm">
                  <thead className="bg-white/[0.03] text-[11px] uppercase tracking-[0.24em] text-slate-500">
                    <tr>
                      <th className="px-4 py-3">Claim</th>
                      <th className="px-4 py-3">Patient</th>
                      <th className="px-4 py-3">Payer</th>
                      <th className="px-4 py-3">Status</th>
                      <th className="px-4 py-3">Created</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/6 bg-black/20">
                    {claims.map((claim, index) => (
                      <tr key={claim.id ?? claim.external_claim_id ?? `claim-row-${index}`} className="hover:bg-white/[0.03]">
                        <td className="px-4 py-4 text-white">{claim.external_claim_id ?? claim.id ?? "Unknown claim"}</td>
                        <td className="px-4 py-4 text-slate-300">{claim.patient_name ?? "Unknown patient"}</td>
                        <td className="px-4 py-4 text-slate-300">{claim.payer_name ?? "Unknown payer"}</td>
                        <td className="px-4 py-4 text-slate-300">{claim.status ?? "Unknown"}</td>
                        <td className="px-4 py-4 text-slate-400">
                          {claim.created_at ? new Date(claim.created_at).toLocaleString() : "Unavailable"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </div>
        </SectionCard>

        <SectionCard title="Object model" subtitle="Every workflow in Revenue OS revolves around a connected revenue object graph.">
          <div className="space-y-3">
            {[
              "Claim",
              "Denial",
              "Encounter",
              "Patient",
              "Payer",
              "Authorization",
              "Documents",
              "Timeline",
            ].map((node) => (
              <div key={node} className="rounded-2xl border border-white/8 bg-black/20 px-4 py-3 text-sm text-white">
                {node}
              </div>
            ))}
          </div>
        </SectionCard>
      </div>

      <SectionCard title="Example drill-downs" subtitle="Mock objects show the intended drawer-driven workflow even when live data is sparse.">
        <div className="grid gap-4 xl:grid-cols-3">
          {exampleObjects.map((item) => (
            <div key={item.id} className="rounded-[22px] border border-white/8 bg-black/20 p-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-[11px] uppercase tracking-[0.24em] text-slate-500">{item.claimId}</p>
                  <h3 className="mt-1 text-lg font-semibold text-white">{item.patient}</h3>
                </div>
                <span className="rounded-full bg-white/6 px-3 py-1 text-xs text-slate-300">{item.denialCode}</span>
              </div>
              <p className="mt-3 text-sm leading-6 text-slate-300">{item.denialReason}</p>
              <div className="mt-4 grid gap-2 text-sm text-slate-400">
                <p>Payer: <span className="text-slate-200">{item.payer}</span></p>
                <p>Authorization: <span className="text-slate-200">{item.authorizationId}</span></p>
                <p>Next step: <span className="text-slate-200">{item.nextAction}</span></p>
              </div>
            </div>
          ))}
        </div>
      </SectionCard>

      <div className="flex gap-3">
        <Link
          href="/dashboard"
          className="inline-flex rounded-full border border-white/10 bg-white/6 px-4 py-2 text-sm font-medium text-white transition hover:border-white/20 hover:bg-white/10"
        >
          Back to queue
        </Link>
        <Link
          href="/era"
          className="inline-flex rounded-full border border-white/10 px-4 py-2 text-sm font-medium text-slate-300 transition hover:border-white/20 hover:text-white"
        >
          Open ERA pipeline
        </Link>
      </div>
    </PageShell>
  );
}
