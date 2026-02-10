"use client";

import type { ComponentType } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { BRANDING } from "@/lib/branding";

type NavItem = {
  href: string;
  label: string;
  description: string;
  icon: ComponentType<{ className?: string }>;
  roles?: string[];
};

type NavSection = {
  label: string;
  items: NavItem[];
};

const ROLE_ADMIN = "Administrator";
const ROLE_COMPLIANCE = "Compliance Manager";
const ROLE_BILLING = "Billing";
const ROLE_STAFF = "Staff";
const ROLE_CLINICIAN = "Clinician";
const ROLE_THERAPIST = "Therapist";
const ROLE_PROVIDER = "Medical Provider";
const ROLE_ASSISTANT = "Medical Assistant";
const ROLE_CONSULTANT = "Consultant";

function IconPulse({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className={className}>
      <path d="M3 12h4l2.5-5 5 10 2.5-5H21" />
    </svg>
  );
}

function IconGrid({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className={className}>
      <rect x="3" y="3" width="8" height="8" rx="2" />
      <rect x="13" y="3" width="8" height="8" rx="2" />
      <rect x="3" y="13" width="8" height="8" rx="2" />
      <rect x="13" y="13" width="8" height="8" rx="2" />
    </svg>
  );
}

function IconUsers({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className={className}>
      <circle cx="9" cy="8" r="3" />
      <circle cx="17" cy="8" r="3" />
      <path d="M3 19a6 6 0 0 1 12 0" />
      <path d="M14 19a5 5 0 0 1 7 0" />
    </svg>
  );
}

function IconCalendar({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className={className}>
      <rect x="4" y="5" width="16" height="15" rx="2" />
      <path d="M8 3v4M16 3v4M4 10h16" />
    </svg>
  );
}

function IconClipboard({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className={className}>
      <rect x="6" y="4" width="12" height="16" rx="2" />
      <path d="M9 4.5h6" />
      <path d="M9 10h6M9 14h4" />
    </svg>
  );
}

function IconShield({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className={className}>
      <path d="M12 3l8 4v6c0 5-3.5 7.5-8 9-4.5-1.5-8-4-8-9V7l8-4z" />
      <path d="M9 12l2 2 4-4" />
    </svg>
  );
}

function IconBank({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className={className}>
      <path d="M3 10h18" />
      <path d="M5 10v7M10 10v7M14 10v7M19 10v7" />
      <path d="M2 20h20" />
      <path d="M12 3l9 5H3l9-5z" />
    </svg>
  );
}

function IconPlug({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className={className}>
      <path d="M7 3v6M11 3v6M6 9h6v2a4 4 0 0 1-4 4H7v6" />
      <path d="M13 15h5" />
    </svg>
  );
}

function IconBuilding({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className={className}>
      <path d="M4 21h16" />
      <path d="M6 21V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v16" />
      <path d="M9 7h1M14 7h1M9 11h1M14 11h1M9 15h1M14 15h1" />
    </svg>
  );
}

function IconWindow({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className={className}>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="M3 9h18" />
      <path d="M8 4v5" />
    </svg>
  );
}

function IconSliders({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className={className}>
      <path d="M4 21v-7M4 10V3M12 21v-4M12 13V3M20 21v-9M20 8V3" />
      <path d="M1 14h6M9 13h6M17 8h6" />
    </svg>
  );
}

const navSections: NavSection[] = [
  {
    label: "Organization",
    items: [
      {
        href: "/organization/home",
        label: "Home",
        description: "Staff operations dashboard",
        icon: IconBuilding,
      },
      {
        href: "/organization/settings",
        label: "Settings",
        description: "Tiles and announcements",
        icon: IconSliders,
        roles: [ROLE_ADMIN],
      },
    ],
  },
  {
    label: "Clinical",
    items: [
      { href: "/dashboard", label: "Dashboard", description: "Clinical and ops view", icon: IconGrid },
      { href: "/patients", label: "Patients", description: "Unified patient charts", icon: IconUsers },
      { href: "/encounters", label: "Encounters", description: "Visits and sessions", icon: IconCalendar },
      { href: "/forms-builder", label: "Forms Builder", description: "Template and versions", icon: IconClipboard },
    ],
  },
  {
    label: "Administration",
    items: [
      {
        href: "/administration",
        label: "Administration",
        description: "Org settings and users",
        icon: IconGrid,
        roles: [ROLE_ADMIN, ROLE_STAFF],
      },
    ],
  },
  {
    label: "Billing",
    items: [
      {
        href: "/billing",
        label: "Billing Workspace",
        description: "Claims and reimbursement",
        icon: IconBank,
        roles: [ROLE_ADMIN, ROLE_BILLING],
      },
    ],
  },
  {
    label: "Compliance",
    items: [
      {
        href: "/audit-center",
        label: "Audit Center",
        description: "Clinical compliance and review",
        icon: IconShield,
        roles: [ROLE_ADMIN, ROLE_COMPLIANCE, ROLE_CONSULTANT],
      },
    ],
  },
  {
    label: "Scheduling",
    items: [
      {
        href: "/scheduling",
        label: "Scheduling",
        description: "Calendars and assignments",
        icon: IconCalendar,
        roles: [ROLE_ADMIN, ROLE_STAFF, ROLE_CLINICIAN, ROLE_THERAPIST, ROLE_PROVIDER, ROLE_ASSISTANT],
      },
    ],
  },
  {
    label: "SharePoint",
    items: [
      {
        href: "/sharepoint",
        label: "SharePoint",
        description: "Organization SharePoint home",
        icon: IconWindow,
      },
    ],
  },
  {
    label: "Integrations",
    items: [
      {
        href: "/integrations",
        label: "Integrations",
        description: "Connector catalog",
        icon: IconPlug,
        roles: [ROLE_ADMIN, ROLE_COMPLIANCE],
      },
    ],
  },
];

function hasRoleAccess(role: string | null | undefined, allowedRoles?: string[]) {
  if (!allowedRoles || allowedRoles.length === 0) return true;
  if (!role) return false;
  return allowedRoles.includes(role);
}

type SidebarProps = {
  role?: string | null;
};

export default function Sidebar({ role = null }: SidebarProps) {
  const pathname = usePathname();
  const visibleSections = navSections
    .map((section) => ({
      ...section,
      items: section.items.filter((item) => hasRoleAccess(role, item.roles)),
    }))
    .filter((section) => section.items.length > 0);

  return (
    <aside className="flex h-full min-h-0 flex-col gap-7 overflow-hidden rounded-xl border border-slate-900 bg-[var(--ui-nav-bg)] p-5 text-[var(--ui-nav-inactive-fg)] lg:sticky lg:top-6 lg:h-[calc(100vh-3rem)]">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-slate-800 text-[var(--ui-nav-active-fg)]">
          <IconPulse className="h-5 w-5" />
        </div>
        <div>
          <div className="text-lg font-semibold tracking-tight text-[var(--ui-nav-active-fg)]">{BRANDING.name}</div>
          <div className="text-[10px] font-semibold uppercase tracking-[0.28em] text-slate-500">{BRANDING.tagline}</div>
        </div>
      </div>

      <nav className="min-h-0 flex-1 space-y-6 overflow-y-auto pr-1">
        {visibleSections.map((section) => (
          <div key={section.label} className="space-y-3">
            <div className="text-[10px] font-semibold uppercase tracking-[0.28em] text-slate-500">{section.label}</div>
            <div className="grid gap-2">
              {section.items.map((item) => {
                const isActive = pathname === item.href || pathname?.startsWith(`${item.href}/`);
                const Icon = item.icon;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`group relative flex items-start gap-3 rounded-lg px-3 py-2.5 transition-colors duration-150 ${
                      isActive
                        ? "bg-[var(--ui-nav-active-bg)] text-[var(--ui-nav-active-fg)]"
                        : "bg-transparent text-[var(--ui-nav-inactive-fg)] hover:bg-[var(--ui-nav-hover-bg)]"
                    }`}
                    data-active={isActive}
                    aria-current={isActive ? "page" : undefined}
                  >
                    <span
                      className={`absolute left-0 top-1/2 h-8 w-[5px] -translate-y-1/2 rounded-r ${
                        isActive ? "bg-[var(--ui-nav-color)]" : "bg-transparent"
                      }`}
                    />
                    <span
                      className={`flex h-8 w-8 items-center justify-center ${
                        isActive
                          ? "rounded-md bg-white/10 text-[var(--ui-nav-active-fg)]"
                          : "text-[var(--ui-nav-inactive-icon)] group-hover:text-[var(--ui-nav-inactive-fg)]"
                      }`}
                    >
                      <Icon className="h-4 w-4" />
                    </span>
                    <div className="space-y-1">
                      <span className={`text-sm font-semibold ${isActive ? "text-[var(--ui-nav-active-fg)]" : "text-[var(--ui-nav-inactive-fg)]"}`}>
                        {item.label}
                      </span>
                      <span className={`block text-[11px] leading-4 ${isActive ? "text-slate-300" : "text-slate-500 group-hover:text-slate-400"}`}>
                        {item.description}
                      </span>
                    </div>
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      <div className="mt-auto space-y-3 text-xs text-slate-400">
        <div className="rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2.5">
          <div className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-400">
            <span className="h-2 w-2 rounded-full bg-[var(--ui-status-success)]" />
            {BRANDING.environmentLabel}
          </div>
          <p className="mt-2 text-[11px] text-slate-500">Service-aware charting and audit visibility.</p>
        </div>
        <div className="text-[10px] text-slate-500">{BRANDING.internalNote}</div>
      </div>
    </aside>
  );
}
