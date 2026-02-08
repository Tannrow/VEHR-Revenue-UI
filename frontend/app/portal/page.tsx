"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  PortalApiError,
  clearPortalAccessToken,
  getPortalAccessToken,
  portalFetch,
} from "@/lib/portal";

type PortalMe = {
  patient_id: string;
  organization_id: string;
  first_name: string;
  last_name: string;
  email?: string | null;
  required_count: number;
  sent_count: number;
  completed_count: number;
};

type PortalTemplateSummary = {
  id: string;
  name: string;
  version: number;
  schema_json: string;
};

type PortalDocumentItem = {
  id: string;
  status: "required" | "sent" | "completed" | "expired";
  expires_at?: string | null;
  completed_at?: string | null;
  sent_at?: string | null;
  template: PortalTemplateSummary;
};

type PortalDocumentGroup = {
  service: {
    id: string;
    name: string;
    code: string;
    category: string;
  };
  documents: PortalDocumentItem[];
};

type PortalSubmitResponse = {
  patient_document_id: string;
  form_submission_id: string;
  status: string;
  completed_at: string;
};

function toErrorMessage(error: unknown, fallback: string) {
  if (error instanceof PortalApiError || error instanceof Error) {
    return error.message || fallback;
  }
  return fallback;
}

function statusBadgeClass(status: PortalDocumentItem["status"]) {
  if (status === "required") return "border-amber-200 bg-amber-50 text-amber-700";
  if (status === "sent") return "border-cyan-200 bg-cyan-50 text-cyan-700";
  if (status === "completed") return "border-emerald-200 bg-emerald-50 text-emerald-700";
  return "border-slate-200 bg-slate-100 text-slate-700";
}

export default function PortalDashboardPage() {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [me, setMe] = useState<PortalMe | null>(null);
  const [groups, setGroups] = useState<PortalDocumentGroup[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [signatureByDocId, setSignatureByDocId] = useState<Record<string, string>>({});
  const [jsonByDocId, setJsonByDocId] = useState<Record<string, string>>({});
  const [submittingDocId, setSubmittingDocId] = useState<string | null>(null);

  const pendingDocuments = useMemo(
    () =>
      groups
        .flatMap((group) => group.documents)
        .filter((document) => document.status === "required" || document.status === "sent"),
    [groups],
  );

  const refreshPortal = useCallback(
    async (portalToken: string) => {
      try {
        setLoading(true);
        setError(null);
        const [meResponse, documentsResponse] = await Promise.all([
          portalFetch<PortalMe>("/api/v1/portal/me", {}, portalToken),
          portalFetch<PortalDocumentGroup[]>("/api/v1/portal/documents", {}, portalToken),
        ]);
        setMe(meResponse);
        setGroups(documentsResponse);
      } catch (loadError) {
        if (loadError instanceof PortalApiError && loadError.status === 401) {
          clearPortalAccessToken();
          router.replace("/portal/login");
          return;
        }
        setError(toErrorMessage(loadError, "Failed to load portal"));
      } finally {
        setLoading(false);
      }
    },
    [router],
  );

  useEffect(() => {
    const existingToken = getPortalAccessToken();
    if (!existingToken) {
      router.replace("/portal/login");
      return;
    }
    setToken(existingToken);
    refreshPortal(existingToken);
  }, [refreshPortal, router]);

  function handleSignOut() {
    clearPortalAccessToken();
    router.replace("/portal/login");
  }

  async function submitDocument(documentId: string) {
    if (!token) return;
    const signature = signatureByDocId[documentId]?.trim();
    if (!signature) {
      setError("Signature name is required before submitting.");
      return;
    }

    let submittedData: Record<string, unknown> = {};
    const rawJson = jsonByDocId[documentId]?.trim();
    if (rawJson) {
      try {
        const parsed = JSON.parse(rawJson);
        if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
          setError("Form response JSON must be a JSON object.");
          return;
        }
        submittedData = parsed as Record<string, unknown>;
      } catch {
        setError("Form response JSON is invalid.");
        return;
      }
    }

    try {
      setSubmittingDocId(documentId);
      setError(null);
      await portalFetch<PortalSubmitResponse>(
        `/api/v1/portal/documents/${documentId}/submit`,
        {
          method: "POST",
          body: JSON.stringify({
            signature_name: signature,
            submitted_data: submittedData,
          }),
        },
        token,
      );
      await refreshPortal(token);
    } catch (submitError) {
      setError(toErrorMessage(submitError, "Failed to submit form"));
    } finally {
      setSubmittingDocId(null);
    }
  }

  if (loading) {
    return (
      <div className="mx-auto max-w-5xl px-4 py-8">
        <p className="text-sm text-slate-600">Loading portal...</p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6 px-4 py-8">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.32em] text-slate-400">
            Patient Portal
          </p>
          <h1 className="text-3xl font-semibold tracking-tight text-slate-900">
            {me?.first_name} {me?.last_name}
          </h1>
          <p className="text-sm text-slate-500">Forms grouped by enrolled service.</p>
        </div>
        <Button type="button" variant="outline" onClick={handleSignOut}>
          Sign Out
        </Button>
      </div>

      {error ? (
        <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
          {error}
        </div>
      ) : null}

      <div className="grid gap-4 md:grid-cols-3">
        <Card className="border-slate-200/70 shadow-sm">
          <CardHeader><CardTitle className="text-base">Required</CardTitle></CardHeader>
          <CardContent className="text-sm text-slate-700">{me?.required_count ?? 0}</CardContent>
        </Card>
        <Card className="border-slate-200/70 shadow-sm">
          <CardHeader><CardTitle className="text-base">Sent</CardTitle></CardHeader>
          <CardContent className="text-sm text-slate-700">{me?.sent_count ?? 0}</CardContent>
        </Card>
        <Card className="border-slate-200/70 shadow-sm">
          <CardHeader><CardTitle className="text-base">Completed</CardTitle></CardHeader>
          <CardContent className="text-sm text-slate-700">{me?.completed_count ?? 0}</CardContent>
        </Card>
      </div>

      {groups.length === 0 ? (
        <Card className="border-slate-200/70 shadow-sm">
          <CardContent className="pt-6 text-sm text-slate-600">
            No portal forms available right now.
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {groups.map((group) => (
            <Card key={group.service.id} className="border-slate-200/70 shadow-sm">
              <CardHeader className="border-b border-slate-200/70 bg-slate-50/70">
                <CardTitle className="text-base">
                  {group.service.name} ({group.service.code})
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4 pt-5">
                {group.documents.map((document) => {
                  const isPending = document.status === "required" || document.status === "sent";
                  return (
                    <div key={document.id} className="rounded-xl border border-slate-200 bg-white p-4">
                      <div className="flex flex-wrap items-center gap-2">
                        <div className="text-sm font-semibold text-slate-900">
                          {document.template.name} v{document.template.version}
                        </div>
                        <Badge className={statusBadgeClass(document.status)}>{document.status}</Badge>
                      </div>

                      {document.expires_at ? (
                        <div className="mt-2 text-xs text-slate-500">
                          Expires: {new Date(document.expires_at).toLocaleString()}
                        </div>
                      ) : null}

                      {isPending ? (
                        <div className="mt-3 space-y-2">
                          <label className="grid gap-1 text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">
                            Form Responses (JSON Object)
                            <textarea
                              className="min-h-[96px] rounded-md border border-slate-200 px-3 py-2 text-sm font-mono text-slate-700"
                              value={jsonByDocId[document.id] ?? ""}
                              onChange={(event) =>
                                setJsonByDocId((current) => ({
                                  ...current,
                                  [document.id]: event.target.value,
                                }))
                              }
                              placeholder='{"question":"answer"}'
                            />
                          </label>

                          <label className="grid gap-1 text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">
                            Signature Name
                            <Input
                              value={signatureByDocId[document.id] ?? ""}
                              onChange={(event) =>
                                setSignatureByDocId((current) => ({
                                  ...current,
                                  [document.id]: event.target.value,
                                }))
                              }
                              placeholder="Type full legal name"
                            />
                          </label>

                          <Button
                            type="button"
                            onClick={() => submitDocument(document.id)}
                            disabled={submittingDocId === document.id}
                          >
                            {submittingDocId === document.id ? "Submitting..." : "Sign & Submit"}
                          </Button>
                        </div>
                      ) : (
                        <div className="mt-3 text-sm text-slate-600">
                          {document.status === "completed"
                            ? `Completed ${document.completed_at ? new Date(document.completed_at).toLocaleString() : ""}`
                            : "This form is no longer submittable."}
                        </div>
                      )}
                    </div>
                  );
                })}
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {pendingDocuments.length === 0 ? (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
          All current portal forms are completed.
        </div>
      ) : null}
    </div>
  );
}
