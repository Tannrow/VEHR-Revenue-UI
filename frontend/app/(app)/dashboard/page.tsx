"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { CircleDollarSign } from "lucide-react";

import MetricCard from "../_components/MetricCard";
import { DataListRow } from "@/components/enterprise/data-list-row";
import { SectionCard } from "@/components/enterprise/section-card";
import { SidebarNav, type SidebarNavGroup } from "@/components/enterprise/sidebar-nav";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError, apiFetch } from "@/lib/api";
import { AppLayoutPageConfig, useAppLayoutConfig } from "@/lib/app-layout-config";
import {
  createTask,
  listTasks,
  taskDueBucket,
  taskScopeOptionsForRole,
  type TaskPriority,
  type TaskRecord,
  type TaskScope,
} from "@/lib/tasks";

type ClientRecord = {
  id: string;
  first_name?: string | null;
  last_name?: string | null;
};

type MeResponse = {
  id: string;
  email: string;
  full_name?: string | null;
  role: string;
  organization_id: string;
};

type AuditSummaryResponse = {
  window_hours: number;
  total_events: number;
};

type AuditAnomaly = {
  kind: string;
  severity: string;
  description: string;
  sample_time: string;
  related_actor?: string | null;
};

type AuditEvent = {
  id: string;
  actor?: string | null;
  action: string;
  entity_type: string;
  entity_id: string;
  created_at: string;
};

type TaskCreateFormState = {
  title: string;
  description: string;
  dueAtLocal: string;
  priority: TaskPriority;
};

type ClientRiskAlert = {
  id: string;
  clientId?: string;
  displayName: string;
  reason: string;
  severityLabel: string;
  severityTone: "critical" | "attention" | "informational";
  isPlaceholder?: boolean;
};

type RevenueSignal = {
  id: string;
  label: string;
  countLabel: string;
  detail: string;
  tone: "critical" | "attention" | "informational";
};

type ComplianceFeedItem = {
  id: string;
  summary: string;
  metadata: string;
  createdAt: string;
};

const DEFAULT_CREATE_FORM: TaskCreateFormState = {
  title: "",
  description: "",
  dueAtLocal: "",
  priority: "normal",
};

function toErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError || error instanceof Error) {
    return error.message || fallback;
  }
  return fallback;
}

function toIsoOrNull(localDateTime: string): string | null {
  if (!localDateTime) {
    return null;
  }
  const parsed = new Date(localDateTime);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }
  return parsed.toISOString();
}

function fullNameForClient(client: ClientRecord): string {
  const first = (client.first_name ?? "").trim();
  const last = (client.last_name ?? "").trim();
  const combined = `${first} ${last}`.trim();
  if (combined) return combined;
  return `Client ${client.id.slice(0, 8)}`;
}

function initialsFromName(value: string): string {
  const parts = value.split(/\s+/).filter(Boolean);
  if (parts.length >= 2) {
    return `${parts[0].slice(0, 1)}${parts[1].slice(0, 1)}`.toUpperCase();
  }
  return value.slice(0, 2).toUpperCase();
}

function severityToneFromTask(task: TaskRecord): "critical" | "attention" | "informational" {
  if (task.priority === "urgent") return "critical";
  const dueBucket = taskDueBucket(task.due_at);
  if (dueBucket === "overdue") return "critical";
  if (task.priority === "high" || dueBucket === "today") return "attention";
  return "informational";
}

function severityLabelFromTask(task: TaskRecord): string {
  const dueBucket = taskDueBucket(task.due_at);
  if (task.priority === "urgent" || dueBucket === "overdue") return "Critical";
  if (task.priority === "high" || dueBucket === "today") return "Attention";
  return "Monitor";
}

function severityChipClass(tone: "critical" | "attention" | "informational"): string {
  if (tone === "critical") return "ui-status-error";
  if (tone === "attention") return "ui-status-warning";
  return "ui-status-info";
}

function humanizeToken(token: string): string {
  const normalized = token.replace(/[._-]+/g, " ").trim();
  if (!normalized) return "activity";
  return normalized
    .split(/\s+/)
    .map((part) => part.slice(0, 1).toUpperCase() + part.slice(1))
    .join(" ");
}

function describeAuditAction(event: AuditEvent): string {
  const actor = event.actor?.trim() ? event.actor.trim() : "A team member";
  const actionLower = event.action.toLowerCase();
  const entity = humanizeToken(event.entity_type);

  if (actionLower.includes("create") || actionLower.includes("add")) {
    return `${actor} created a ${entity} record.`;
  }
  if (actionLower.includes("update") || actionLower.includes("edit") || actionLower.includes("patch")) {
    return `${actor} updated a ${entity} record.`;
  }
  if (actionLower.includes("delete") || actionLower.includes("remove")) {
    return `${actor} removed a ${entity} record.`;
  }
  if (actionLower.includes("upload")) {
    return `${actor} uploaded a ${entity} document.`;
  }
  if (actionLower.includes("dispatch") || actionLower.includes("send")) {
    return `${actor} sent a ${entity} update.`;
  }
  return `${actor} recorded activity on ${entity}.`;
}

function describeAnomaly(anomaly: AuditAnomaly): string {
  if (anomaly.kind === "burst_activity") {
    return "Compliance monitor detected unusual audit volume in a short window.";
  }
  if (anomaly.kind === "after_hours_write") {
    return "Compliance monitor detected after-hours write activity requiring review.";
  }
  if (anomaly.kind === "high_risk_action") {
    return "Compliance monitor flagged a high-risk operational action for follow-up.";
  }
  return anomaly.description || "Compliance monitor flagged a policy-sensitive event.";
}

function formatMetaTime(value: string): string {
  const stamp = new Date(value);
  if (Number.isNaN(stamp.getTime())) return "Time unavailable";
  return stamp.toLocaleString();
}

function matchesSearch(query: string, values: Array<string | undefined>): boolean {
  if (!query) return true;
  const normalized = query.toLowerCase();
  return values.some((value) => (value ?? "").toLowerCase().includes(normalized));
}

async function safeAuditFetch<T>(path: string): Promise<T | null> {
  try {
    return await apiFetch<T>(path, { cache: "no-store" });
  } catch (error) {
    if (error instanceof ApiError && (error.status === 403 || error.status === 404)) {
      return null;
    }
    throw error;
  }
}

export default function DashboardPage() {
  const { searchQuery } = useAppLayoutConfig();
  const [clients, setClients] = useState<ClientRecord[]>([]);
  const [tasks, setTasks] = useState<TaskRecord[]>([]);
  const [auditSummary, setAuditSummary] = useState<AuditSummaryResponse | null>(null);
  const [auditAnomalies, setAuditAnomalies] = useState<AuditAnomaly[] | null>(null);
  const [auditEvents, setAuditEvents] = useState<AuditEvent[] | null>(null);

  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [isSavingTask, setIsSavingTask] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [createForm, setCreateForm] = useState<TaskCreateFormState>(DEFAULT_CREATE_FORM);

  useEffect(() => {
    let isMounted = true;

    async function loadCommandCenter() {
      setIsLoading(true);
      setLoadError(null);

      try {
        const [me, clientRows] = await Promise.all([
          apiFetch<MeResponse>("/api/v1/auth/me", { cache: "no-store" }),
          apiFetch<ClientRecord[]>("/api/v1/patients", { cache: "no-store" }),
        ]);
        if (!isMounted) return;

        const scopeOptions = taskScopeOptionsForRole(me.role);
        const preferredScope: TaskScope = scopeOptions.includes("all")
          ? "all"
          : scopeOptions.includes("team")
            ? "team"
            : "self";

        const [taskList, summary, anomalies, events] = await Promise.all([
          listTasks({
            scope: preferredScope,
            status: ["open", "in_progress"],
            limit: 200,
          }),
          safeAuditFetch<AuditSummaryResponse>("/api/v1/audit/summary?hours=72"),
          safeAuditFetch<AuditAnomaly[]>("/api/v1/audit/anomalies?hours=72&limit=20"),
          safeAuditFetch<AuditEvent[]>("/api/v1/audit/events?limit=20"),
        ]);

        if (!isMounted) return;

        setClients(clientRows);
        setTasks(taskList.items);
        setAuditSummary(summary);
        setAuditAnomalies(anomalies);
        setAuditEvents(events);
      } catch (error) {
        if (!isMounted) return;
        setLoadError(toErrorMessage(error, "Unable to load command center."));
      } finally {
        if (isMounted) {
          setIsLoading(false);
        }
      }
    }

    void loadCommandCenter();
    return () => {
      isMounted = false;
    };
  }, []);

  const claimsRejectedCount = useMemo(
    () =>
      tasks.filter((task) => {
        const source = `${task.title} ${task.description ?? ""}`.toLowerCase();
        return source.includes("claim") && (source.includes("denied") || source.includes("reject"));
      }).length,
    [tasks],
  );

  const authsExpiringCount = useMemo(() => {
    const now = Date.now();
    const sevenDaysMs = 7 * 24 * 60 * 60 * 1000;
    return tasks.filter((task) => {
      const source = `${task.title} ${task.description ?? ""}`.toLowerCase();
      if (!source.includes("auth")) return false;
      if (!task.due_at) return false;
      const dueMs = new Date(task.due_at).getTime();
      if (Number.isNaN(dueMs)) return false;
      return dueMs >= now && dueMs <= now + sevenDaysMs;
    }).length;
  }, [tasks]);

  const erasToReviewCount = useMemo(
    () =>
      tasks.filter((task) => {
        const source = `${task.title} ${task.description ?? ""}`.toLowerCase();
        return source.includes("era") || source.includes("remittance");
      }).length,
    [tasks],
  );

  const cptMismatchCount = useMemo(() => {
    if (!auditAnomalies) return null;
    return auditAnomalies.filter((item) => {
      const source = `${item.kind} ${item.description}`.toLowerCase();
      return source.includes("cpt") || source.includes("coding") || source.includes("mismatch");
    }).length;
  }, [auditAnomalies]);

  const highRiskAnomalyCount = useMemo(
    () => (auditAnomalies ?? []).filter((item) => item.severity === "high").length,
    [auditAnomalies],
  );

  const mediumRiskAnomalyCount = useMemo(
    () => (auditAnomalies ?? []).filter((item) => item.severity === "medium").length,
    [auditAnomalies],
  );

  const complianceRiskScore = useMemo(() => {
    if (!auditAnomalies) return null;
    const high = auditAnomalies.filter((item) => item.severity === "high").length;
    const medium = auditAnomalies.filter((item) => item.severity === "medium").length;
    const low = auditAnomalies.filter((item) => item.severity !== "high" && item.severity !== "medium").length;
    return Math.min(100, high * 20 + medium * 10 + low * 4);
  }, [auditAnomalies]);

  const clientRiskAlerts = useMemo<ClientRiskAlert[]>(() => {
    const byClientId = new Map(clients.map((client) => [client.id, client]));

    const taskLinkedAlerts: ClientRiskAlert[] = [];
    for (const task of tasks) {
      if ((task.related_type ?? "").toLowerCase() !== "patient" || !task.related_id) {
        continue;
      }
      const client = byClientId.get(task.related_id);
      if (!client) {
        continue;
      }
      taskLinkedAlerts.push({
        id: task.id,
        clientId: client.id,
        displayName: fullNameForClient(client),
        reason: task.title || "Open patient task requires clinical follow-up.",
        severityLabel: severityLabelFromTask(task),
        severityTone: severityToneFromTask(task),
      });
      if (taskLinkedAlerts.length >= 8) {
        break;
      }
    }

    if (taskLinkedAlerts.length > 0) {
      return taskLinkedAlerts;
    }

    if (clients.length === 0) {
      return [
        {
          id: "todo-no-client-data",
          displayName: "No clients available",
          reason: "TODO: connect patient-level risk signal feed.",
          severityLabel: "TODO",
          severityTone: "informational",
          isPlaceholder: true,
        },
      ];
    }

    return clients.slice(0, 6).map((client) => ({
      id: `todo-${client.id}`,
      clientId: client.id,
      displayName: fullNameForClient(client),
      reason: "TODO: connect patient-level risk scoring feed.",
      severityLabel: "TODO",
      severityTone: "informational",
      isPlaceholder: true,
    }));
  }, [clients, tasks]);

  const revenueSignals = useMemo<RevenueSignal[]>(() => {
    return [
      {
        id: "claims-rejected",
        label: "Claims rejected",
        countLabel: `${claimsRejectedCount}`,
        detail: "Derived from open billing-related tasks.",
        tone: claimsRejectedCount > 0 ? "critical" : "informational",
      },
      {
        id: "auth-expiring",
        label: "Authorizations expiring",
        countLabel: `${authsExpiringCount}`,
        detail: "Derived from tasks due within 7 days.",
        tone: authsExpiringCount > 0 ? "attention" : "informational",
      },
      {
        id: "cpt-mismatch",
        label: "High-risk CPT mismatches",
        countLabel: cptMismatchCount === null ? "TODO" : `${cptMismatchCount}`,
        detail:
          cptMismatchCount === null
            ? "TODO: requires audit read access for mismatch signal extraction."
            : "Derived from available anomaly descriptors.",
        tone: cptMismatchCount && cptMismatchCount > 0 ? "critical" : "informational",
      },
      {
        id: "era-review",
        label: "ERAs to review",
        countLabel: `${erasToReviewCount}`,
        detail: "Derived from remittance and ERA task patterns.",
        tone: erasToReviewCount > 0 ? "attention" : "informational",
      },
    ];
  }, [authsExpiringCount, claimsRejectedCount, cptMismatchCount, erasToReviewCount]);

  const complianceFeed = useMemo<ComplianceFeedItem[]>(() => {
    const fromEvents: ComplianceFeedItem[] = (auditEvents ?? []).map((event) => ({
      id: `event-${event.id}`,
      summary: describeAuditAction(event),
      metadata: formatMetaTime(event.created_at),
      createdAt: event.created_at,
    }));

    const fromAnomalies: ComplianceFeedItem[] = (auditAnomalies ?? []).map((anomaly, index) => ({
      id: `anomaly-${index}-${anomaly.sample_time}`,
      summary: describeAnomaly(anomaly),
      metadata: `${humanizeToken(anomaly.severity)} severity - ${formatMetaTime(anomaly.sample_time)}`,
      createdAt: anomaly.sample_time,
    }));

    const combined = [...fromEvents, ...fromAnomalies]
      .sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime())
      .slice(0, 12);

    if (combined.length > 0) {
      return combined;
    }

    return [
      {
        id: "todo-compliance-feed",
        summary: "TODO: connect compliance activity feed (requires audit:read permission).",
        metadata: "No audit activity stream is currently available for this role.",
        createdAt: new Date().toISOString(),
      },
    ];
  }, [auditAnomalies, auditEvents]);

  const filteredRiskAlerts = useMemo(
    () =>
      clientRiskAlerts.filter((alert) =>
        matchesSearch(searchQuery, [alert.displayName, alert.reason, alert.severityLabel]),
      ),
    [clientRiskAlerts, searchQuery],
  );

  const filteredRevenueSignals = useMemo(
    () =>
      revenueSignals.filter((item) =>
        matchesSearch(searchQuery, [item.label, item.detail, item.countLabel]),
      ),
    [revenueSignals, searchQuery],
  );

  const filteredComplianceFeed = useMemo(
    () =>
      complianceFeed.filter((item) =>
        matchesSearch(searchQuery, [item.summary, item.metadata]),
      ),
    [complianceFeed, searchQuery],
  );

  const notificationCount = useMemo(() => {
    const overdueCount = tasks.filter((task) => taskDueBucket(task.due_at) === "overdue").length;
    return overdueCount + highRiskAnomalyCount + mediumRiskAnomalyCount;
  }, [highRiskAnomalyCount, mediumRiskAnomalyCount, tasks]);

  const commandNavGroups = useMemo<SidebarNavGroup[]>(() => {
    return [
      {
        id: "clinical",
        label: "Clinical",
        items: [
          { id: "clinical-clients", label: "Clients", href: "/clients" },
          { id: "clinical-forms", label: "Forms", href: "/forms" },
          { id: "clinical-documents", label: "Documents", href: "/documents" },
        ],
      },
      {
        id: "revenue",
        label: "Revenue",
        items: [
          { id: "revenue-billing", label: "Billing", href: "/billing" },
          { id: "revenue-reports", label: "Reports", href: "/reports" },
        ],
      },
      {
        id: "operations",
        label: "Operations",
        items: [
          { id: "ops-command", label: "Command Center", href: "/dashboard", active: true },
          { id: "ops-calls", label: "Calls & Reception", href: "/calls-reception" },
          { id: "ops-tasks", label: "Tasks", href: "/tasks" },
        ],
      },
      {
        id: "compliance",
        label: "Compliance",
        items: [
          { id: "comp-audit", label: "Audit Center", href: "/audit-center" },
          { id: "comp-workbench", label: "Compliance", href: "/compliance" },
        ],
      },
      {
        id: "system",
        label: "System",
        items: [
          { id: "sys-admin", label: "Admin Center", href: "/admin-center" },
          { id: "sys-integrations", label: "Integrations", href: "/integrations" },
          { id: "sys-org-settings", label: "Organization Settings", href: "/organization/settings" },
        ],
      },
    ];
  }, []);

  async function handleCreateTask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!createForm.title.trim()) {
      setCreateError("Title is required.");
      return;
    }

    setIsSavingTask(true);
    setCreateError(null);
    try {
      await createTask({
        title: createForm.title.trim(),
        description: createForm.description.trim() || null,
        due_at: toIsoOrNull(createForm.dueAtLocal),
        priority: createForm.priority,
      });
      setCreateForm(DEFAULT_CREATE_FORM);
      setIsCreateOpen(false);
    } catch (error) {
      setCreateError(toErrorMessage(error, "Unable to create task."));
    } finally {
      setIsSavingTask(false);
    }
  }

  const topBarActions = useMemo(
    () => (
      <Button type="button" size="sm" onClick={() => setIsCreateOpen(true)}>
        Create Task
      </Button>
    ),
    [],
  );

  return (
    <div className="flex flex-col gap-[var(--space-24)]" data-testid="operations-command-center">
      <AppLayoutPageConfig
        moduleLabel="Operations"
        pageTitle="Clinical Command Center"
        subtitle="Operations dashboard for clinical risk, revenue integrity, and compliance oversight."
        showSearch={true}
        searchPlaceholder="Search clients, revenue, compliance"
        notificationCount={notificationCount}
        actions={topBarActions}
      />

      {isLoading ? <p className="ui-type-meta">Loading command center data...</p> : null}
      {loadError ? (
        <div className="rounded-[var(--radius-6)] border border-[color-mix(in_srgb,var(--status-critical)_25%,white)] bg-[color-mix(in_srgb,var(--status-critical)_8%,white)] px-[var(--space-12)] py-[var(--space-8)] text-[length:var(--font-size-14)] text-[var(--status-critical)]">
          {loadError}
        </div>
      ) : null}

      <div className="grid gap-[var(--space-16)] lg:grid-cols-[280px_minmax(0,1fr)]">
        <aside className="space-y-[var(--space-16)]">
          <SidebarNav groups={commandNavGroups} testId="operations-command-nav" />
          <SectionCard title="Data Coverage" description="Only connected data sources are shown below.">
            <div className="space-y-[var(--space-8)]">
              <p className="ui-type-body text-[var(--neutral-muted)]">
                Active sources: patients, tasks{auditSummary || auditAnomalies || auditEvents ? ", audit." : "."}
              </p>
              {!auditSummary && !auditAnomalies && !auditEvents ? (
                <p className="ui-type-meta text-[var(--status-attention)]">
                  TODO: audit-backed metrics require audit:read permission.
                </p>
              ) : null}
            </div>
          </SectionCard>
        </aside>

        <section className="min-w-0 space-y-[var(--space-16)]">
          <div className="grid gap-[var(--space-16)] sm:grid-cols-2 xl:grid-cols-4">
            <MetricCard label="Active Clients" value={`${clients.length}`} hint="Live patient registry" tone="info" />
            <MetricCard
              label="Pending Claims"
              value={`${claimsRejectedCount}`}
              hint="Proxy from open billing tasks"
              tone={claimsRejectedCount > 0 ? "warn" : "neutral"}
            />
            <MetricCard
              label="A/R Balance"
              value="TODO"
              hint="TODO: connect billing A/R ledger source"
              icon={<CircleDollarSign className="h-4 w-4" />}
              tone="neutral"
            />
            <MetricCard
              label="Compliance Risk"
              value={complianceRiskScore === null ? "TODO" : `${complianceRiskScore}/100`}
              hint={
                complianceRiskScore === null
                  ? "TODO: requires audit access"
                  : `${highRiskAnomalyCount} high-risk findings in 72h`
              }
              tone={
                complianceRiskScore === null
                  ? "neutral"
                  : complianceRiskScore >= 70
                    ? "danger"
                    : complianceRiskScore >= 35
                      ? "warn"
                      : "success"
              }
            />
          </div>

          <div className="grid gap-[var(--space-16)] xl:grid-cols-2">
            <SectionCard title="Client Risk Alerts" description="Patient-linked risk cues for rapid chart review." testId="client-risk-alerts">
              <div className="space-y-[var(--space-8)]">
                {filteredRiskAlerts.length === 0 ? (
                  <p className="ui-type-body text-[var(--neutral-muted)]">No client risk alerts match the current search.</p>
                ) : (
                  filteredRiskAlerts.map((alert) => (
                    <div
                      key={alert.id}
                      className="rounded-[var(--radius-6)] border border-[var(--neutral-border)] bg-[var(--neutral-panel)] px-[var(--space-12)] py-[var(--space-12)] transition-colors hover:bg-[var(--muted)]"
                    >
                      <div className="flex flex-wrap items-start justify-between gap-[var(--space-12)]">
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-[var(--space-8)]">
                            <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-[var(--radius-6)] bg-[var(--accent)] text-[length:var(--font-size-12)] font-semibold text-[var(--accent-foreground)]">
                              {initialsFromName(alert.displayName)}
                            </span>
                            <p className="truncate text-[length:var(--font-size-14)] font-semibold text-[var(--neutral-text)]">
                              {alert.displayName}
                            </p>
                          </div>
                          <p className="ui-type-body mt-[var(--space-8)] text-[var(--neutral-muted)]">{alert.reason}</p>
                        </div>

                        <div className="flex items-center gap-[var(--space-8)]">
                          <span className={`ui-status-pill ${severityChipClass(alert.severityTone)}`}>{alert.severityLabel}</span>
                          {alert.clientId ? (
                            <Button type="button" variant="outline" size="sm" asChild>
                              <Link href={`/patients/${encodeURIComponent(alert.clientId)}`}>View Chart</Link>
                            </Button>
                          ) : (
                            <span className="ui-type-meta">TODO</span>
                          )}
                        </div>
                      </div>
                      {alert.isPlaceholder ? <p className="ui-type-meta mt-[var(--space-8)] text-[var(--status-attention)]">TODO placeholder</p> : null}
                    </div>
                  ))
                )}
              </div>
            </SectionCard>

            <SectionCard title="Revenue Integrity" description="Claims and reimbursement quality checkpoints." testId="revenue-integrity-list">
              <div className="space-y-[var(--space-8)]">
                {filteredRevenueSignals.map((item) => (
                  <DataListRow
                    key={item.id}
                    title={item.label}
                    description={item.detail}
                    statusLabel={item.countLabel}
                    statusTone={item.tone}
                    actions={
                      <Button type="button" variant="outline" size="sm" asChild>
                        <Link href="/billing">Open Billing</Link>
                      </Button>
                    }
                  />
                ))}
                {filteredRevenueSignals.length === 0 ? (
                  <p className="ui-type-body text-[var(--neutral-muted)]">No revenue signals match the current search.</p>
                ) : null}
              </div>
            </SectionCard>
          </div>

          <SectionCard title="Compliance Activity Feed" description="Human-readable governance events for operational follow-up." testId="compliance-activity-feed">
            <div className="space-y-[var(--space-8)]">
              {filteredComplianceFeed.map((item) => (
                <DataListRow
                  key={item.id}
                  title={item.summary}
                  meta={item.metadata}
                  statusLabel="Logged"
                  statusTone="informational"
                />
              ))}
              {filteredComplianceFeed.length === 0 ? (
                <p className="ui-type-body text-[var(--neutral-muted)]">No compliance events match the current search.</p>
              ) : null}
            </div>
          </SectionCard>
        </section>
      </div>

      {isCreateOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/35 px-4">
          <Card className="w-full max-w-lg bg-white shadow-sm">
            <CardHeader className="pb-2">
              <CardTitle className="ui-type-section-title text-[var(--neutral-text)]">Create Task</CardTitle>
            </CardHeader>
            <CardContent className="pt-0">
              <form className="space-y-[var(--space-12)]" onSubmit={handleCreateTask}>
                <div>
                  <label className="mb-[var(--space-4)] block ui-type-meta font-semibold uppercase tracking-[0.12em]" htmlFor="operations-task-title">
                    Title
                  </label>
                  <input
                    id="operations-task-title"
                    type="text"
                    className="h-[var(--space-32)] w-full rounded-[var(--radius-6)] border border-[var(--neutral-border)] bg-[var(--neutral-panel)] px-[var(--space-12)] ui-type-body text-[var(--neutral-text)]"
                    value={createForm.title}
                    onChange={(event) => setCreateForm((current) => ({ ...current, title: event.target.value }))}
                    required
                  />
                </div>

                <div>
                  <label className="mb-[var(--space-4)] block ui-type-meta font-semibold uppercase tracking-[0.12em]" htmlFor="operations-task-description">
                    Description
                  </label>
                  <textarea
                    id="operations-task-description"
                    className="min-h-[var(--space-56)] w-full rounded-[var(--radius-6)] border border-[var(--neutral-border)] bg-[var(--neutral-panel)] px-[var(--space-12)] py-[var(--space-8)] ui-type-body text-[var(--neutral-text)]"
                    value={createForm.description}
                    onChange={(event) => setCreateForm((current) => ({ ...current, description: event.target.value }))}
                  />
                </div>

                <div className="grid gap-[var(--space-12)] sm:grid-cols-2">
                  <div>
                    <label className="mb-[var(--space-4)] block ui-type-meta font-semibold uppercase tracking-[0.12em]" htmlFor="operations-task-due">
                      Due at
                    </label>
                    <input
                      id="operations-task-due"
                      type="datetime-local"
                      className="h-[var(--space-32)] w-full rounded-[var(--radius-6)] border border-[var(--neutral-border)] bg-[var(--neutral-panel)] px-[var(--space-12)] ui-type-body text-[var(--neutral-text)]"
                      value={createForm.dueAtLocal}
                      onChange={(event) => setCreateForm((current) => ({ ...current, dueAtLocal: event.target.value }))}
                    />
                  </div>
                  <div>
                    <label className="mb-[var(--space-4)] block ui-type-meta font-semibold uppercase tracking-[0.12em]" htmlFor="operations-task-priority">
                      Priority
                    </label>
                    <select
                      id="operations-task-priority"
                      className="h-[var(--space-32)] w-full rounded-[var(--radius-6)] border border-[var(--neutral-border)] bg-[var(--neutral-panel)] px-[var(--space-12)] ui-type-body text-[var(--neutral-text)]"
                      value={createForm.priority}
                      onChange={(event) =>
                        setCreateForm((current) => ({
                          ...current,
                          priority: event.target.value as TaskPriority,
                        }))
                      }
                    >
                      <option value="low">Low</option>
                      <option value="normal">Normal</option>
                      <option value="high">High</option>
                      <option value="urgent">Urgent</option>
                    </select>
                  </div>
                </div>

                {createError ? <p className="ui-type-body text-[var(--status-critical)]">{createError}</p> : null}

                <div className="flex justify-end gap-[var(--space-8)] pt-[var(--space-4)]">
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => {
                      setIsCreateOpen(false);
                      setCreateError(null);
                      setCreateForm(DEFAULT_CREATE_FORM);
                    }}
                  >
                    Cancel
                  </Button>
                  <Button type="submit" disabled={isSavingTask}>
                    {isSavingTask ? "Saving..." : "Create Task"}
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>
        </div>
      ) : null}
    </div>
  );
}
