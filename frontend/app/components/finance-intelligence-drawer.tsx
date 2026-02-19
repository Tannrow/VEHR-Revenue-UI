"use client";
import { Copy, Loader2, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { FinanceAIEnvelope } from "@/lib/finance-ai";

type FinanceIntelligenceDrawerProps = {
  open: boolean;
  title?: string;
  loading?: boolean;
  error?: string | null;
  payload?: FinanceAIEnvelope | null;
  onClose: () => void;
};

function copyText(value: string) {
  if (typeof navigator === "undefined" || !value) return;
  void navigator.clipboard.writeText(value);
}

function SectionHeading({ label }: { label: string }) {
  return <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</p>;
}

export function FinanceIntelligenceDrawer({ open, title, loading, error, payload, onClose }: FinanceIntelligenceDrawerProps) {
  const advisory = payload?.advisory;

  const combinedDrafts = advisory?.drafts?.length
    ? advisory.drafts.map((draft) => `${draft.type}: ${draft.content}`).join("\n\n")
    : "No drafts prepared.";

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[var(--z-drawer)] flex justify-end bg-black/40 backdrop-blur-sm">
      <div className="h-full w-full max-w-2xl bg-[var(--neutral-panel)] shadow-[var(--shadow-lg)]">
        <div className="flex items-start justify-between border-b border-[color-mix(in_srgb,var(--neutral-border)_75%,white)] px-6 py-4">
          <div className="space-y-1">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">AI Advisory</p>
            <h2 className="text-xl font-semibold text-slate-900">{title ?? "Finance Intelligence"}</h2>
            {payload ? (
              <p className="text-xs text-slate-500">
                Context pack {payload.context_pack_version} • Generated {new Date(payload.generated_at).toLocaleString()}
              </p>
            ) : null}
          </div>
          <div className="flex items-center gap-2">
            {payload ? <Badge variant="secondary">Risk {payload.risk_score}</Badge> : null}
            <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close drawer">
              <X className="h-4 w-4" />
            </Button>
          </div>
        </div>

        <div className="flex h-[calc(100%-76px)] flex-col gap-4 overflow-y-auto px-6 py-5">
          {loading ? (
            <div className="flex items-center gap-3 rounded-lg border border-dashed border-slate-200 bg-white px-4 py-3 text-sm text-slate-700">
              <Loader2 className="h-4 w-4 animate-spin" />
              Generating intelligence…
            </div>
          ) : null}
          {error ? (
            <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
              {error}
            </div>
          ) : null}

          {advisory ? (
            <>
              <div className="rounded-lg border border-[var(--border)] bg-white p-4 shadow-sm">
                <div className="flex items-center justify-between">
                  <SectionHeading label="Summary" />
                  <Button variant="ghost" size="icon" onClick={() => copyText(advisory.summary)} aria-label="Copy summary">
                    <Copy className="h-4 w-4" />
                  </Button>
                </div>
                <p className="mt-2 text-sm text-slate-800">{advisory.summary}</p>
              </div>

              <div className="rounded-lg border border-[var(--border)] bg-white p-4 shadow-sm">
                <div className="flex items-center justify-between">
                  <SectionHeading label="Root Cause" />
                  <Button variant="ghost" size="icon" onClick={() => copyText(advisory.root_cause)} aria-label="Copy root cause">
                    <Copy className="h-4 w-4" />
                  </Button>
                </div>
                <p className="mt-2 text-sm text-slate-800">{advisory.root_cause}</p>
              </div>

              <div className="rounded-lg border border-[var(--border)] bg-white p-4 shadow-sm">
                <div className="flex items-center justify-between">
                  <SectionHeading label="Recommended Actions" />
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => copyText(advisory.recommended_actions.map((item) => item.action).join("\n"))}
                    aria-label="Copy recommended actions"
                  >
                    <Copy className="h-4 w-4" />
                  </Button>
                </div>
                <div className="mt-3 space-y-3">
                  {advisory.recommended_actions.length === 0 ? (
                    <p className="text-sm text-slate-600">No actions provided.</p>
                  ) : (
                    advisory.recommended_actions.map((item, index) => (
                      <div key={`${item.action}-${index}`} className="flex items-start justify-between gap-3 rounded-md border border-slate-200 bg-slate-50 px-3 py-2">
                        <div>
                          <p className="text-sm font-semibold text-slate-900">{item.action}</p>
                          <p className="text-xs text-slate-500">Impact {item.impact_estimate}</p>
                        </div>
                        <Badge variant="outline">{item.urgency}</Badge>
                      </div>
                    ))
                  )}
                </div>
              </div>

              <details open className="rounded-lg border border-[var(--border)] bg-white p-4 shadow-sm">
                <summary className="flex cursor-pointer items-center justify-between">
                  <SectionHeading label="Drafts" />
                  <Button variant="ghost" size="icon" onClick={() => copyText(combinedDrafts)} aria-label="Copy drafts">
                    <Copy className="h-4 w-4" />
                  </Button>
                </summary>
                <div className="mt-3 space-y-2">
                  {advisory.drafts.length === 0 ? (
                    <p className="text-sm text-slate-600">No drafts provided.</p>
                  ) : (
                    advisory.drafts.map((draft, index) => (
                      <div key={`${draft.type}-${index}`} className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2">
                        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{draft.type}</p>
                        <p className="text-sm text-slate-800">{draft.content}</p>
                      </div>
                    ))
                  )}
                </div>
              </details>

              <div className="rounded-lg border border-[var(--border)] bg-white p-4 shadow-sm">
                <SectionHeading label="Questions Needed" />
                <ul className="mt-2 list-disc space-y-1 pl-4 text-sm text-slate-800">
                  {advisory.questions_needed.length === 0 ? <li>None listed.</li> : advisory.questions_needed.map((item, idx) => <li key={`${item}-${idx}`}>{item}</li>)}
                </ul>
              </div>

              <div className="rounded-lg border border-[var(--border)] bg-white p-4 shadow-sm">
                <SectionHeading label="Assumptions" />
                <ul className="mt-2 list-disc space-y-1 pl-4 text-sm text-slate-800">
                  {advisory.assumptions.length === 0 ? <li>No assumptions provided.</li> : advisory.assumptions.map((item, idx) => <li key={`${item}-${idx}`}>{item}</li>)}
                </ul>
              </div>

              <div className="rounded-lg border border-[var(--border)] bg-white p-4 shadow-sm">
                <SectionHeading label="Confidence" />
                <div className="mt-2 flex items-center gap-2">
                  <Badge variant="secondary">{advisory.confidence} confidence</Badge>
                  <Badge variant="outline">AI advisory only</Badge>
                </div>
              </div>
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}
