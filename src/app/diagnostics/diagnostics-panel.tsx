"use client";

import { useEffect, useState } from "react";

import { apiClientFetch } from "@/lib/api/client";

type HealthStatus = "pending" | "ok" | "error";
type AuthStatus = "pending" | "authenticated" | "unauthenticated";

type AuthMeResponse = {
  id: string;
  email: string;
  full_name?: string | null;
  role: string;
  organization_id: string;
};

type MCPToolHealth = {
  name: string;
  status: string;
  ok: boolean;
  detail: string;
  checked_at: string;
  latency_ms?: number | null;
  repo?: string | null;
  default_branch?: string | null;
  sample_resource_group?: string | null;
};

type MCPHealthResponse = {
  ok: boolean;
  checked_at: string;
  tools: {
    azure: MCPToolHealth;
    postgres: MCPToolHealth;
    github: MCPToolHealth;
  };
};

type DiagnosticsState = {
  healthStatus: HealthStatus;
  authStatus: AuthStatus;
  orgId: string | null;
  mcpHealth: MCPHealthResponse | null;
  mcpError: string | null;
};

const INITIAL_STATE: DiagnosticsState = {
  healthStatus: "pending",
  authStatus: "pending",
  orgId: null,
  mcpHealth: null,
  mcpError: null,
};

function statusBadgeClasses(status: "healthy" | "warning" | "error" | "pending"): string {
  switch (status) {
    case "healthy":
      return "border-emerald-500/40 bg-emerald-500/10 text-emerald-200";
    case "warning":
      return "border-amber-500/40 bg-amber-500/10 text-amber-200";
    case "error":
      return "border-rose-500/40 bg-rose-500/10 text-rose-200";
    case "pending":
    default:
      return "border-zinc-700 bg-black/30 text-zinc-300";
  }
}

function StatusBadge({ label, tone }: { label: string; tone: "healthy" | "warning" | "error" | "pending" }) {
  return (
    <span className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold uppercase tracking-wide ${statusBadgeClasses(tone)}`}>
      {label}
    </span>
  );
}

function getErrorMessage(response: Awaited<ReturnType<typeof apiClientFetch>>, fallback: string): string {
  if (response.data && typeof response.data === "object" && "detail" in response.data) {
    const detail = (response.data as { detail?: unknown }).detail;
    if (typeof detail === "string" && detail.trim()) {
      return detail.trim();
    }
  }

  if (response.data && typeof response.data === "object" && "error" in response.data) {
    const error = (response.data as { error?: unknown }).error;
    if (typeof error === "string" && error.trim()) {
      return error.trim();
    }
  }

  if (response.text.trim()) {
    return response.text.trim();
  }

  return fallback;
}

function ToolCard({ tool }: { tool: MCPToolHealth }) {
  const tone = tool.ok ? "healthy" : tool.status === "missing_config" ? "warning" : "error";

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold capitalize text-white">{tool.name}</p>
          <p className="mt-2 text-sm leading-6 text-zinc-400 break-words">{tool.detail}</p>
        </div>
        <StatusBadge
          label={tool.ok ? "Healthy" : tool.status === "missing_config" ? "Missing config" : "Error"}
          tone={tone}
        />
      </div>

      <div className="mt-4 space-y-1 text-xs text-zinc-500">
        {typeof tool.latency_ms === "number" ? <p>Latency: {tool.latency_ms} ms</p> : null}
        {tool.repo ? <p>Repo: {tool.repo}</p> : null}
        {tool.default_branch ? <p>Branch: {tool.default_branch}</p> : null}
        {tool.sample_resource_group ? <p>Sample RG: {tool.sample_resource_group}</p> : null}
        <p>Checked: {new Date(tool.checked_at).toLocaleString()}</p>
      </div>
    </div>
  );
}

export function DiagnosticsPanel() {
  const [state, setState] = useState<DiagnosticsState>(INITIAL_STATE);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      const [healthResponse, authResponse, mcpResponse] = await Promise.all([
        apiClientFetch("/api/health"),
        apiClientFetch("/api/auth/me"),
        apiClientFetch("/api/mcp-health"),
      ]);

      if (cancelled) {
        return;
      }

      setState({
        healthStatus: healthResponse.ok ? "ok" : "error",
        authStatus: authResponse.ok ? "authenticated" : "unauthenticated",
        orgId: authResponse.ok && authResponse.data && typeof authResponse.data === "object"
          ? ((authResponse.data as AuthMeResponse).organization_id ?? null)
          : null,
        mcpHealth: mcpResponse.ok && mcpResponse.data && typeof mcpResponse.data === "object"
          ? (mcpResponse.data as MCPHealthResponse)
          : null,
        mcpError: mcpResponse.ok ? null : getErrorMessage(mcpResponse, "Unable to load MCP diagnostics."),
      });
    }

    void load();
    const intervalId = window.setInterval(() => {
      void load();
    }, 30000);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, []);

  const overallTone =
    state.mcpHealth === null
      ? "pending"
      : state.mcpHealth.ok
        ? "healthy"
        : "warning";

  return (
    <div className="space-y-6 text-sm text-zinc-300">
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-4">
          <p className="text-xs uppercase tracking-[0.18em] text-zinc-500">Backend health</p>
          <div className="mt-3">
            {state.healthStatus === "pending" ? <StatusBadge label="Checking" tone="pending" /> : null}
            {state.healthStatus === "ok" ? <StatusBadge label="Healthy" tone="healthy" /> : null}
            {state.healthStatus === "error" ? <StatusBadge label="Unreachable" tone="error" /> : null}
          </div>
        </div>

        <div className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-4">
          <p className="text-xs uppercase tracking-[0.18em] text-zinc-500">Auth status</p>
          <div className="mt-3">
            {state.authStatus === "pending" ? <StatusBadge label="Checking" tone="pending" /> : null}
            {state.authStatus === "authenticated" ? <StatusBadge label="Authenticated" tone="healthy" /> : null}
            {state.authStatus === "unauthenticated" ? <StatusBadge label="Unauthenticated" tone="error" /> : null}
          </div>
        </div>

        <div className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-4">
          <p className="text-xs uppercase tracking-[0.18em] text-zinc-500">Organization</p>
          <p className="mt-3 break-all text-sm font-semibold text-white">{state.orgId ?? "Unavailable"}</p>
        </div>

        <div className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-4">
          <p className="text-xs uppercase tracking-[0.18em] text-zinc-500">MCP status</p>
          <div className="mt-3">
            <StatusBadge
              label={
                state.mcpHealth === null
                  ? "Checking"
                  : state.mcpHealth.ok
                    ? "All healthy"
                    : "Attention needed"
              }
              tone={overallTone}
            />
          </div>
          {state.mcpHealth ? (
            <p className="mt-3 text-xs text-zinc-500">
              Last checked: {new Date(state.mcpHealth.checked_at).toLocaleString()}
            </p>
          ) : null}
        </div>
      </div>

      {state.mcpError ? (
        <div className="rounded-md border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-amber-200">
          {state.mcpError}
        </div>
      ) : null}

      <div className="grid gap-4 md:grid-cols-3">
        {state.mcpHealth ? (
          Object.values(state.mcpHealth.tools).map((tool) => <ToolCard key={tool.name} tool={tool} />)
        ) : (
          <>
            <div className="h-40 animate-pulse rounded-xl border border-zinc-800 bg-zinc-950/40" />
            <div className="h-40 animate-pulse rounded-xl border border-zinc-800 bg-zinc-950/40" />
            <div className="h-40 animate-pulse rounded-xl border border-zinc-800 bg-zinc-950/40" />
          </>
        )}
      </div>
    </div>
  );
}
