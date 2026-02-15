export type ModuleId =
  | "care_delivery"
  | "call_center"
  | "workforce"
  | "revenue_cycle"
  | "governance"
  | "administration";

export type ModuleNavItem = {
  label: string;
  href: string;
  external?: boolean;
  requiredAnyPermissions?: string[];
};

export type ModuleDefinition = {
  id: ModuleId;
  name: string;
  description: string;
  defaultRoute: string;
  navItems: ModuleNavItem[];
};

const MODULE_DEFINITIONS: ModuleDefinition[] = [
  {
    id: "care_delivery",
    name: "Care Delivery",
    description: "Client workflows, forms, documents, and task execution.",
    defaultRoute: "/clients",
    navItems: [
      { label: "Clients", href: "/clients", requiredAnyPermissions: ["clients:read", "patients:read"] },
      { label: "Forms", href: "/forms", requiredAnyPermissions: ["forms:read"] },
      { label: "Documents", href: "/documents", requiredAnyPermissions: ["documents:read"] },
      {
        label: "Tasks",
        href: "/tasks",
        requiredAnyPermissions: ["tasks:read_self", "tasks:read_team", "tasks:read_all"],
      },
    ],
  },
  {
    id: "call_center",
    name: "Call Center",
    description: "Reception, call handling, conversion pipeline, and activity monitoring.",
    defaultRoute: "/calls-reception",
    navItems: [
      { label: "Calls & Reception", href: "/calls-reception", requiredAnyPermissions: ["calls:read"] },
      { label: "Pipeline", href: "/pipeline", requiredAnyPermissions: ["leads:read", "calls:read"] },
      { label: "Activity Log", href: "/activity-log", requiredAnyPermissions: ["calls:read"] },
    ],
  },
  {
    id: "workforce",
    name: "Workforce Management",
    description: "Staffing, attendance, payroll tools, and manager operations.",
    defaultRoute: "/staff",
    navItems: [
      { label: "Staff", href: "/staff", requiredAnyPermissions: ["staff:read"] },
      { label: "Time & Attendance", href: "/time-attendance", requiredAnyPermissions: ["workforce:read", "staff:read"] },
      { label: "Clock In/Out", href: "https://tsheets.intuit.com/ip/#_SwitchJC", external: true },
      { label: "Payroll", href: "/payroll", requiredAnyPermissions: ["billing:read", "workforce:approve_time", "admin:org_settings"] },
      {
        label: "QuickBooks Time (Managers)",
        href: "https://tsheets.intuit.com/",
        external: true,
        requiredAnyPermissions: ["workforce:approve_time", "admin:org_settings"],
      },
    ],
  },
  {
    id: "revenue_cycle",
    name: "Revenue Cycle",
    description: "Billing and revenue operations.",
    defaultRoute: "/billing",
    navItems: [
      { label: "Billing", href: "/billing", requiredAnyPermissions: ["billing:read", "billing:write"] },
    ],
  },
  {
    id: "governance",
    name: "Governance",
    description: "Audit controls, compliance oversight, and quality safeguards.",
    defaultRoute: "/audit-center",
    navItems: [
      { label: "Audit Center", href: "/audit-center", requiredAnyPermissions: ["audit:read", "audits:read"] },
      { label: "Analytics", href: "/analytics/chart_audit", requiredAnyPermissions: ["analytics:view"] },
      { label: "Compliance", href: "/compliance", requiredAnyPermissions: ["compliance:read"] },
    ],
  },
  {
    id: "administration",
    name: "Administration",
    description: "Operational controls and organization-level administration.",
    defaultRoute: "/dashboard",
    navItems: [
      {
        label: "Operations",
        href: "/dashboard",
        requiredAnyPermissions: ["tasks:read_self", "tasks:read_team", "tasks:read_all", "clients:read"],
      },
      { label: "Admin Center", href: "/admin-center", requiredAnyPermissions: ["admin:org_settings", "users:manage"] },
    ],
  },
];

const PATH_MODULE_MATCHERS: Array<{ prefix: string; moduleId: ModuleId }> = [
  { prefix: "/calls-reception", moduleId: "call_center" },
  { prefix: "/pipeline", moduleId: "call_center" },
  { prefix: "/activity-log", moduleId: "call_center" },
  { prefix: "/call-center", moduleId: "call_center" },
  { prefix: "/call-center-test", moduleId: "call_center" },

  { prefix: "/staff", moduleId: "workforce" },
  { prefix: "/time-attendance", moduleId: "workforce" },
  { prefix: "/payroll", moduleId: "workforce" },

  { prefix: "/billing", moduleId: "revenue_cycle" },

  { prefix: "/audit-center", moduleId: "governance" },
  { prefix: "/analytics", moduleId: "governance" },
  { prefix: "/compliance", moduleId: "governance" },

  { prefix: "/clients", moduleId: "care_delivery" },
  { prefix: "/forms", moduleId: "care_delivery" },
  { prefix: "/documents", moduleId: "care_delivery" },
  { prefix: "/tasks", moduleId: "care_delivery" },
  { prefix: "/patients", moduleId: "care_delivery" },
  { prefix: "/encounters", moduleId: "care_delivery" },

  { prefix: "/dashboard", moduleId: "administration" },
  { prefix: "/admin-center", moduleId: "administration" },
  { prefix: "/administration", moduleId: "administration" },
  { prefix: "/integrations", moduleId: "administration" },
  { prefix: "/organization", moduleId: "administration" },
  { prefix: "/sharepoint", moduleId: "administration" },
  { prefix: "/admin", moduleId: "administration" },
  { prefix: "/crm", moduleId: "administration" },
  { prefix: "/scheduling", moduleId: "administration" },
  { prefix: "/referrals", moduleId: "administration" },
  { prefix: "/reports", moduleId: "administration" },
];

export function listModules(): ModuleDefinition[] {
  return MODULE_DEFINITIONS;
}

export function getModuleById(moduleId: ModuleId): ModuleDefinition {
  const found = MODULE_DEFINITIONS.find((item) => item.id === moduleId);
  if (!found) {
    throw new Error(`Unknown module: ${moduleId}`);
  }
  return found;
}

export function isModuleId(value: string | null | undefined): value is ModuleId {
  if (!value) return false;
  return MODULE_DEFINITIONS.some((item) => item.id === value);
}

export function resolveModuleForPath(pathname: string | null | undefined): ModuleId | null {
  if (!pathname || !pathname.startsWith("/")) return null;
  if (pathname === "/directory") return null;

  for (const entry of PATH_MODULE_MATCHERS) {
    if (pathname === entry.prefix || pathname.startsWith(`${entry.prefix}/`)) {
      return entry.moduleId;
    }
  }
  return "administration";
}

export function hasAnyPermission(
  grantedPermissions: Set<string>,
  requiredAnyPermissions: string[] | undefined,
): boolean {
  if (!requiredAnyPermissions || requiredAnyPermissions.length === 0) {
    return true;
  }
  return requiredAnyPermissions.some((permission) => grantedPermissions.has(permission));
}

export function visibleModuleNavItems(moduleId: ModuleId, grantedPermissions: Set<string>): ModuleNavItem[] {
  const moduleDef = getModuleById(moduleId);
  return moduleDef.navItems.filter((item) => hasAnyPermission(grantedPermissions, item.requiredAnyPermissions));
}

export function pageTitleForPath(pathname: string | null | undefined, moduleId: ModuleId | null): string {
  if (!pathname || !moduleId) {
    return "Organizational Directory";
  }

  if (pathname === "/sharepoint" || pathname.startsWith("/sharepoint/")) {
    return "Organization Information";
  }
  if (pathname === "/organization/home" || pathname.startsWith("/organization/home/")) {
    return "Organization Information";
  }

  const moduleDef = getModuleById(moduleId);
  for (const item of moduleDef.navItems) {
    if (!item.external && (pathname === item.href || pathname.startsWith(`${item.href}/`))) {
      return item.label;
    }
  }

  const segment = pathname.split("/").filter(Boolean).slice(-1)[0] ?? "overview";
  return segment
    .split("-")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function defaultRouteForModule(moduleId: ModuleId): string {
  return getModuleById(moduleId).defaultRoute;
}
