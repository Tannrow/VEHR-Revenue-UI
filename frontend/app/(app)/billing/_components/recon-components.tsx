"use client";

import type { ChangeEvent, DragEvent } from "react";
import { useEffect, useRef, useState } from "react";
import { FileText, UploadCloud, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";

export type ReconClaimRow = {
  id: number;
  account_id?: string | null;
  match_status: string;
  billed_total?: number | string | null;
  paid_total?: number | string | null;
  variance_total?: number | string | null;
  line_count?: number | null;
  reason_code?: string | null;
};

export type ReconLineRow = {
  id: number;
  account_id?: string | null;
  dos_from?: string | null;
  dos_to?: string | null;
  proc_code?: string | null;
  billed_amount?: number | string | null;
  paid_amount?: number | string | null;
  variance_amount?: number | string | null;
  match_status: string;
  reason_code?: string | null;
};

type UploadCardProps = {
  title: string;
  description?: string;
  file: File | null;
  accept?: string;
  disabled?: boolean;
  onFileChange: (file: File | null) => void;
  onError?: (message: string) => void;
};

type SummaryStatCardProps = {
  label: string;
  value: string | number | null | undefined;
  hint?: string;
};

type ReconciliationSectionProps = {
  title: string;
  rows: ReconClaimRow[];
  totals: {
    billed: string;
    paid: string;
    variance: string;
  };
  onSelect?: (row: ReconClaimRow) => void;
};

type ClaimDetailDrawerProps = {
  open: boolean;
  claim: ReconClaimRow | null;
  lines: ReconLineRow[];
  loading: boolean;
  error?: string | null;
  note?: string | null;
  onClose: () => void;
};

type LineFiltersBarProps = {
  matchStatus: string;
  billedTrack: string;
  onMatchStatusChange: (value: string) => void;
  onBilledTrackChange: (value: string) => void;
};

type PaginationControlsProps = {
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
  onPageChange: (page: number) => void;
};

function formatBytes(size?: number): string {
  if (size == null) return "";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function isPdfFile(file: File): boolean {
  const type = file.type?.toLowerCase() ?? "";
  if (type === "application/pdf") return true;
  return file.name.toLowerCase().endsWith(".pdf");
}

export function UploadCard({
  title,
  description,
  file,
  accept = "application/pdf",
  disabled,
  onFileChange,
  onError,
}: UploadCardProps) {
  const [dragActive, setDragActive] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const selected = event.target.files?.[0] ?? null;
    if (!selected) return;
    if (!isPdfFile(selected)) {
      onError?.("Please upload a PDF file.");
      return;
    }
    onFileChange(selected);
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    event.stopPropagation();
    setDragActive(false);
    const selected = event.dataTransfer.files?.[0] ?? null;
    if (!selected) return;
    if (!isPdfFile(selected)) {
      onError?.("Please upload a PDF file.");
      return;
    }
    onFileChange(selected);
  }

  function openPicker() {
    inputRef.current?.click();
  }

  return (
    <Card
      className={cn(
        "border border-dashed border-[color-mix(in_srgb,var(--neutral-border)_70%,white)] bg-[var(--neutral-panel)] transition",
        dragActive ? "border-primary/60 bg-primary/5" : "hover:border-[color-mix(in_srgb,var(--neutral-border)_90%,black)]",
      )}
      onDragOver={(event) => {
        event.preventDefault();
        setDragActive(true);
      }}
      onDragLeave={() => setDragActive(false)}
      onDrop={handleDrop}
    >
      <CardHeader className="space-y-1">
        <CardTitle className="text-base text-slate-900">{title}</CardTitle>
        {description ? <p className="text-sm text-slate-500">{description}</p> : null}
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <input
          ref={inputRef}
          type="file"
          accept={accept}
          className="hidden"
          onChange={handleFileChange}
          disabled={disabled}
        />
        {file ? (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white px-3 py-2">
            <div className="flex items-center gap-2">
              <FileText className="h-4 w-4 text-slate-500" />
              <div>
                <p className="text-sm font-semibold text-slate-800">{file.name}</p>
                <p className="text-xs text-slate-500">{formatBytes(file.size)}</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Button type="button" variant="outline" size="sm" onClick={openPicker} disabled={disabled}>
                Replace
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => onFileChange(null)}
                disabled={disabled}
              >
                <X className="h-4 w-4" />
                Remove
              </Button>
            </div>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed border-slate-200 bg-white px-4 py-6 text-center">
            <UploadCloud className="h-6 w-6 text-slate-400" />
            <p className="text-sm text-slate-600">Drag and drop a PDF here, or</p>
            <Button type="button" variant="outline" size="sm" onClick={openPicker} disabled={disabled}>
              Choose file
            </Button>
            <p className="text-xs text-slate-400">PDF only</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export function SummaryStatCard({ label, value, hint }: SummaryStatCardProps) {
  return (
    <Card className="bg-[var(--neutral-panel)]">
      <CardContent className="space-y-1 p-4">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">{label}</p>
        <p className="text-xl font-semibold text-slate-900">{value ?? "—"}</p>
        {hint ? <p className="text-xs text-slate-500">{hint}</p> : null}
      </CardContent>
    </Card>
  );
}

export function ReconciliationSection({ title, rows, totals, onSelect }: ReconciliationSectionProps) {
  return (
    <Card className="bg-white shadow-sm">
      <CardHeader className="flex flex-row items-center justify-between gap-4">
        <div>
          <CardTitle className="text-lg text-slate-900">{title}</CardTitle>
          <p className="text-xs text-slate-500">Billed {totals.billed} · Paid {totals.paid} · Variance {totals.variance}</p>
        </div>
        <Badge variant="secondary">{rows.length} claims</Badge>
      </CardHeader>
      <CardContent>
        {rows.length === 0 ? (
          <p className="text-sm text-slate-500">No claims in this section.</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Claim ID</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Billed</TableHead>
                <TableHead className="text-right">Paid</TableHead>
                <TableHead className="text-right">Variance</TableHead>
                <TableHead className="text-right">Lines</TableHead>
                <TableHead>Reason</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow
                  key={row.id}
                  className={onSelect ? "cursor-pointer" : undefined}
                  onClick={() => onSelect?.(row)}
                >
                  <TableCell className="font-medium text-slate-900">{row.account_id ?? "—"}</TableCell>
                  <TableCell>{row.match_status}</TableCell>
                  <TableCell className="text-right">{row.billed_total ?? "—"}</TableCell>
                  <TableCell className="text-right">{row.paid_total ?? "—"}</TableCell>
                  <TableCell className="text-right">{row.variance_total ?? "—"}</TableCell>
                  <TableCell className="text-right">{row.line_count ?? "—"}</TableCell>
                  <TableCell className="text-slate-500">{row.reason_code ?? "—"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}

export function ClaimDetailDrawer({
  open,
  claim,
  lines,
  loading,
  error,
  note,
  onClose,
}: ClaimDetailDrawerProps) {
  if (!open || !claim) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <button
        type="button"
        className="absolute inset-0 bg-black/30"
        onClick={onClose}
        aria-label="Close claim details"
      />
      <div className="relative z-10 h-full w-full max-w-2xl overflow-y-auto bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
          <div>
            <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Claim</p>
            <h2 className="text-xl font-semibold text-slate-900">{claim.account_id ?? "Unlinked claim"}</h2>
          </div>
          <Button type="button" variant="ghost" onClick={onClose}>
            <X className="h-4 w-4" />
            Close
          </Button>
        </div>
        <div className="space-y-4 px-6 py-4">
          <div className="grid gap-3 sm:grid-cols-3">
            <SummaryStatCard label="Status" value={claim.match_status} />
            <SummaryStatCard label="Billed" value={claim.billed_total ?? "—"} />
            <SummaryStatCard label="Paid" value={claim.paid_total ?? "—"} />
          </div>
          {note ? (
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-800">
              {note}
            </div>
          ) : null}
          {error ? (
            <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-700">
              {error}
            </div>
          ) : null}
          {loading ? (
            <p className="text-sm text-slate-500">Loading line items...</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>DOS</TableHead>
                  <TableHead>Procedure</TableHead>
                  <TableHead className="text-right">Billed</TableHead>
                  <TableHead className="text-right">Paid</TableHead>
                  <TableHead className="text-right">Variance</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {lines.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={6} className="text-sm text-slate-500">
                      No line items found for this claim.
                    </TableCell>
                  </TableRow>
                ) : (
                  lines.map((line) => (
                    <TableRow key={line.id}>
                      <TableCell>
                        {line.dos_from ?? "—"}
                        {line.dos_to && line.dos_to !== line.dos_from ? ` - ${line.dos_to}` : ""}
                      </TableCell>
                      <TableCell>{line.proc_code ?? "—"}</TableCell>
                      <TableCell className="text-right">{line.billed_amount ?? "—"}</TableCell>
                      <TableCell className="text-right">{line.paid_amount ?? "—"}</TableCell>
                      <TableCell className="text-right">{line.variance_amount ?? "—"}</TableCell>
                      <TableCell>{line.match_status}</TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          )}
        </div>
      </div>
    </div>
  );
}

export function LineFiltersBar({
  matchStatus,
  billedTrack,
  onMatchStatusChange,
  onBilledTrackChange,
}: LineFiltersBarProps) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <label className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
        Match status
        <select
          className="mt-1 h-9 w-full rounded-[var(--radius-6)] border border-[color-mix(in_srgb,var(--neutral-border)_72%,white)] bg-[var(--neutral-panel)] px-3 text-sm text-slate-800 shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
          value={matchStatus}
          onChange={(event) => onMatchStatusChange(event.target.value)}
        >
          <option value="">All</option>
          <option value="matched">Matched</option>
          <option value="unmatched_billed">Unmatched billed</option>
          <option value="unmatched_era">Unmatched ERA</option>
          <option value="needs_review">Needs review</option>
        </select>
      </label>
      <label className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
        Billed PDF type
        <select
          className="mt-1 h-9 w-full rounded-[var(--radius-6)] border border-[color-mix(in_srgb,var(--neutral-border)_72%,white)] bg-[var(--neutral-panel)] px-3 text-sm text-slate-800 shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
          value={billedTrack}
          onChange={(event) => onBilledTrackChange(event.target.value)}
        >
          <option value="">All</option>
          <option value="CHPW">CHPW</option>
          <option value="Coordinated Care">Coordinated Care</option>
          <option value="Wellpoint">Wellpoint</option>
          <option value="Billing">Billing</option>
        </select>
      </label>
    </div>
  );
}

export function PaginationControls({
  page,
  pageSize,
  total,
  totalPages,
  onPageChange,
}: PaginationControlsProps) {
  const [pageInput, setPageInput] = useState(String(page));

  useEffect(() => {
    setPageInput(String(page));
  }, [page]);

  function syncInput(value: number) {
    setPageInput(String(value));
  }

  function handleJump() {
    const parsed = Number.parseInt(pageInput, 10);
    if (!Number.isFinite(parsed)) return;
    const nextPage = Math.min(Math.max(1, parsed), totalPages || 1);
    syncInput(nextPage);
    onPageChange(nextPage);
  }

  const start = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const end = Math.min(page * pageSize, total);

  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <p className="text-sm text-slate-500">
        Showing {start}-{end} of {total}
      </p>
      <div className="flex items-center gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => onPageChange(Math.max(1, page - 1))}
          disabled={page <= 1}
        >
          Prev
        </Button>
        <div className="flex items-center gap-2 text-sm text-slate-600">
          Page {page} of {Math.max(totalPages, 1)}
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => onPageChange(Math.min(totalPages || 1, page + 1))}
          disabled={page >= totalPages}
        >
          Next
        </Button>
        <div className="flex items-center gap-2">
          <input
            className="h-8 w-16 rounded-[var(--radius-6)] border border-[color-mix(in_srgb,var(--neutral-border)_72%,white)] bg-[var(--neutral-panel)] px-2 text-sm"
            value={pageInput}
            onChange={(event) => setPageInput(event.target.value)}
            onBlur={handleJump}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                handleJump();
              }
            }}
          />
          <Button type="button" variant="ghost" size="sm" onClick={handleJump}>
            Jump
          </Button>
        </div>
      </div>
    </div>
  );
}
