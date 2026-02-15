export type ReportCategory = "executive" | "revenue" | "clinical" | "compliance" | "other";

export type ReportCatalogEntry = {
  key: string;
  title: string;
  description: string;
  category: ReportCategory;
  defaultKpis: string[];
};

const REPORT_CATALOG: Record<string, ReportCatalogEntry> = {
  chart_audit: {
    key: "chart_audit",
    title: "Chart Audit",
    description: "Audit readiness, documentation quality, and clinical compliance signals.",
    category: "compliance",
    defaultKpis: ["unsigned_notes_over_24h", "unsigned_notes_over_72h", "active_clients", "encounters_week"],
  },
  executive_overview: {
    key: "executive_overview",
    title: "Executive Overview",
    description: "High-level census, revenue, operational throughput, and risk signals.",
    category: "executive",
    defaultKpis: [
      "active_clients",
      "encounters_week",
      "charges_week",
      "claims_paid_week",
      "denial_rate_week",
      "unsigned_notes_over_72h",
    ],
  },
  revenue_cycle: {
    key: "revenue_cycle",
    title: "Revenue Cycle",
    description: "Charges, payments, denial trends, and accounts receivable indicators.",
    category: "revenue",
    defaultKpis: [
      "charges_week",
      "claims_submitted_week",
      "claims_paid_week",
      "denial_rate_week",
      "ar_balance_total",
      "ar_over_30",
    ],
  },
  clinical_delivery: {
    key: "clinical_delivery",
    title: "Clinical Delivery",
    description: "Service delivery throughput, attendance, and clinical operations coverage.",
    category: "clinical",
    defaultKpis: [
      "encounters_week",
      "active_clients",
      "attendance_rate_week",
      "no_show_rate_week",
      "new_admissions_week",
      "discharges_week",
    ],
  },
  compliance_risk: {
    key: "compliance_risk",
    title: "Compliance & Risk",
    description: "Compliance exposure and documentation risk indicators across the org.",
    category: "compliance",
    defaultKpis: ["unsigned_notes_over_24h", "unsigned_notes_over_72h", "active_clients", "denial_rate_week"],
  },
  // Backward-compatible alias (older key name).
  exec_overview: {
    key: "exec_overview",
    title: "Executive Overview",
    description: "High-level census, revenue, operational throughput, and risk signals.",
    category: "executive",
    defaultKpis: [
      "active_clients",
      "encounters_week",
      "charges_week",
      "claims_paid_week",
      "denial_rate_week",
      "unsigned_notes_over_72h",
    ],
  },
};

export function getReportCatalogEntry(reportKey: string): ReportCatalogEntry | null {
  const normalized = reportKey.trim().toLowerCase();
  return REPORT_CATALOG[normalized] ?? null;
}

export function catalogTitleForReportKey(reportKey: string): string {
  const entry = getReportCatalogEntry(reportKey);
  if (entry) {
    return entry.title;
  }
  const normalizedKey = reportKey.trim();
  if (!normalizedKey) {
    return "Analytics";
  }
  return normalizedKey
    .split("_")
    .filter(Boolean)
    .map((part) => `${part.slice(0, 1).toUpperCase()}${part.slice(1)}`)
    .join(" ");
}

export type UserRoleKey =
  | "admin"
  | "office_manager"
  | "sud_supervisor"
  | "billing"
  | "compliance"
  | "clinician"
  | "therapist"
  | "medical_provider"
  | "medical_assistant"
  | string;

export function allowedCategoriesForRole(role: UserRoleKey): ReportCategory[] {
  const normalized = (role ?? "").trim().toLowerCase();
  if (normalized === "admin" || normalized === "office_manager" || normalized === "sud_supervisor") {
    return ["executive", "revenue", "clinical", "compliance", "other"];
  }
  if (normalized === "billing") {
    return ["revenue"];
  }
  if (
    normalized === "clinician"
    || normalized === "therapist"
    || normalized === "medical_provider"
    || normalized === "medical_assistant"
  ) {
    return ["clinical"];
  }
  if (normalized === "compliance") {
    return ["compliance"];
  }
  return [];
}

export function isReportAllowedForRole(reportKey: string, role: UserRoleKey): boolean {
  const allowed = allowedCategoriesForRole(role);
  if (allowed.length === 0) {
    return false;
  }
  const entry = getReportCatalogEntry(reportKey);
  if (!entry) {
    return allowed.includes("other");
  }
  return allowed.includes(entry.category);
}

export function defaultKpisForReport(reportKey: string): string[] {
  const entry = getReportCatalogEntry(reportKey);
  if (entry) {
    return entry.defaultKpis;
  }
  return ["active_clients", "encounters_week", "charges_week", "unsigned_notes_over_72h"];
}

