"use client";

import { useEffect, useMemo, useState } from "react";
import { CloudUpload, Play, RefreshCw, ShieldAlert } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ApiError, apiFetch } from "@/lib/api";

type EraFile = {
  id: string;
  file_name: string;
  status: string;
  payer_name_raw?: string | null;
  received_date?: string | null;
  error_detail?: string | null;
  created_at: string;
};

type WorkItem = {
  id: string;
  type: string;
  payer_name: string;
  claim_ref: string;
  dollars_cents: number;
  status: string;
  created_at: string;
};

function formatCentsToDollars(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`;
}

function statusVariant(status: string) {
  const normalized = status.toUpperCase();
  if (normalized === "NORMALIZED" || normalized === "COMPLETED") return "default";
  if (normalized === "ERROR") return "destructive";
  if (normalized === "EXTRACTED" || normalized === "STRUCTURED") return "secondary";
  return "outline";
}

export default function EraIntakePage() {
  const [files, setFiles] = useState<EraFile[]>([]);
  const [worklist, setWorklist] = useState<WorkItem[]>([]);
  const [selectedFiles, setSelectedFiles] = useState<FileList | null>(null);
  const [uploading, setUploading] = useState(false);
  const [processingId, setProcessingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const hasSelection = useMemo(() => selectedFiles && selectedFiles.length > 0, [selectedFiles]);

  useEffect(() => {
    void refreshData();
  }, []);

  async function refreshData() {
    setError(null);
    try {
        const [fileRows, workItems] = await Promise.all([
        apiFetch<EraFile[]>("/api/v1/revenue/era-pdfs", { cache: "no-store" }),
        apiFetch<WorkItem[]>("/api/v1/revenue/era-worklist", { cache: "no-store" }),
      ]);
      setFiles(fileRows);
      setWorklist(workItems);
    } catch (err) {
      setError(toError(err, "Failed to load ERA data."));
    }
  }

  async function handleUpload(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedFiles || selectedFiles.length === 0) return;
    setError(null);
    setUploading(true);
    try {
      const form = new FormData();
      Array.from(selectedFiles).forEach((file) => form.append("files", file, file.name));
      await apiFetch<EraFile[]>("/api/v1/revenue/era-pdfs/upload", {
        method: "POST",
        body: form,
      });
      setSelectedFiles(null);
      await refreshData();
    } catch (err) {
      setError(toError(err, "Upload failed."));
    } finally {
      setUploading(false);
    }
  }

  async function processFile(id: string) {
    setError(null);
    setProcessingId(id);
    try {
      await apiFetch<EraFile>(`/api/v1/revenue/era-pdfs/${encodeURIComponent(id)}/process`, {
        method: "POST",
      });
      await refreshData();
    } catch (err) {
      setError(toError(err, "Processing failed."));
    } finally {
      setProcessingId(null);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="space-y-2">
        <p className="text-sm font-semibold text-slate-500">Revenue</p>
        <h1 className="text-[2rem] font-semibold tracking-tight text-slate-900">ERA Intake</h1>
        <p className="max-w-3xl text-base text-slate-600">
          Upload ERA PDFs, run extraction, and work the prioritized items without exposing PHI.
        </p>
      </div>

      {error ? (
        <div className="flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-800">
          <ShieldAlert className="h-4 w-4" />
          <span>{error}</span>
        </div>
      ) : null}

      <form onSubmit={handleUpload} className="grid gap-4 md:grid-cols-[1fr_1.1fr]">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between gap-3">
            <div>
              <CardTitle>Upload ERA PDFs</CardTitle>
              <p className="text-sm text-slate-500">Multi-file upload supported.</p>
            </div>
            <CloudUpload className="h-5 w-5 text-slate-400" />
          </CardHeader>
          <CardContent className="space-y-4">
            <input
              type="file"
              multiple
              accept="application/pdf"
              onChange={(e) => setSelectedFiles(e.target.files)}
              className="w-full rounded-md border border-slate-200 p-2 text-sm"
            />
            <div className="flex items-center gap-3">
              <Button type="submit" disabled={!hasSelection || uploading}>
                {uploading ? "Uploading…" : "Upload"}
              </Button>
              <Button type="button" variant="ghost" onClick={() => setSelectedFiles(null)}>
                Clear
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between gap-2">
            <CardTitle>ERA Files</CardTitle>
            <Button variant="ghost" size="icon" onClick={() => void refreshData()} aria-label="Refresh files">
              <RefreshCw className="h-4 w-4" />
            </Button>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>File</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Payer</TableHead>
                  <TableHead>Received</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {files.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={5} className="text-center text-sm text-slate-500">
                      No ERA uploads yet.
                    </TableCell>
                  </TableRow>
                ) : (
                  files.map((file) => (
                    <TableRow key={file.id}>
                      <TableCell className="font-medium">{file.file_name}</TableCell>
                      <TableCell>
                        <Badge variant={statusVariant(file.status)}>{file.status}</Badge>
                        {file.error_detail ? (
                          <div className="text-xs text-rose-600">{file.error_detail}</div>
                        ) : null}
                      </TableCell>
                      <TableCell className="text-sm text-slate-700">{file.payer_name_raw || "—"}</TableCell>
                      <TableCell className="text-sm text-slate-700">
                        {file.received_date ? new Date(file.received_date).toLocaleDateString() : "—"}
                      </TableCell>
                      <TableCell className="text-right">
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => void processFile(file.id)}
                          disabled={processingId === file.id}
                        >
                          <Play className="mr-1 h-4 w-4" />
                          {processingId === file.id ? "Processing…" : "Process"}
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </form>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-2">
          <CardTitle>Worklist</CardTitle>
          <Button variant="ghost" size="icon" onClick={() => void refreshData()} aria-label="Refresh worklist">
            <RefreshCw className="h-4 w-4" />
          </Button>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Type</TableHead>
                <TableHead>Payer</TableHead>
                <TableHead>Claim Ref</TableHead>
                <TableHead>Dollars</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {worklist.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={5} className="text-center text-sm text-slate-500">
                    No open work items.
                  </TableCell>
                </TableRow>
              ) : (
                worklist.map((item) => (
                  <TableRow key={item.id}>
                    <TableCell className="font-medium">{item.type}</TableCell>
                    <TableCell className="text-sm text-slate-700">{item.payer_name}</TableCell>
                    <TableCell className="text-sm text-slate-700">{item.claim_ref}</TableCell>
                    <TableCell className="text-sm text-slate-900">{formatCentsToDollars(item.dollars_cents)}</TableCell>
                    <TableCell>
                      <Badge variant={statusVariant(item.status)}>{item.status}</Badge>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}

function toError(error: unknown, fallback: string): string {
  if (error instanceof ApiError && error.message) return error.message;
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}
