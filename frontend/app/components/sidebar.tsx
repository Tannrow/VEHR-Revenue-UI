"use client";

import type { ComponentType } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { BRANDING } from "@/lib/branding";

type NavItem = {
  href: string;
  label: string;
  icon: ComponentType<{ className?: string }>;
  external?: boolean;
  visibleToRoles?: string[];
};

type NavSection = {
  label: string;
  items: NavItem[];
};

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

function IconTask({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className={className}>
      <path d="M8 6h12M8 12h12M8 18h12" />
      <path d="M3 6l1.5 1.5L6.5 5.5M3 12l1.5 1.5L6.5 11.5M3 18l1.5 1.5L6.5 17.5" />
    </svg>
  );
}

function IconPhone({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className={className}>
      <path d="M22 16.9v3a2 2 0 0 1-2.2 2A19.9 19.9 0 0 1 11 18.6 19.5 19.5 0 0 1 5.4 13 19.9 19.9 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7 12.9 12.9 0 0 0 .7 2.8 2 2 0 0 1-.5 2.1L8 10a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.5 12.9 12.9 0 0 0 2.8.7A2 2 0 0 1 22 16.9Z" />
    </svg>
  );
}

function IconPipeline({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className={className}>
      <path d="M3 5h18" />
      <path d="M6 5v5a3 3 0 0 0 3 3h1a3 3 0 0 1 3 3v3" />
      <path d="M18 5v3a3 3 0 0 1-3 3h-2" />
      <path d="M13 19h8" />
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

function IconUserBadge({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className={className}>
      <circle cx="12" cy="8" r="4" />
      <path d="M4 20a8 8 0 0 1 16 0" />
      <path d="M19 3v4M17 5h4" />
    </svg>
  );
}

function IconActivity({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className={className}>
      <path d="M3 12h4l2-5 4 10 2-5h6" />
    </svg>
  );
}

function IconDocuments({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className={className}>
      <path d="M4 5a2 2 0 0 1 2-2h5l2 2h5a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2Z" />
      <path d="M9 12h6M9 16h4" />
    </svg>
  );
}

function IconForm({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className={className}>
      <rect x="4" y="3" width="16" height="18" rx="2" />
      <path d="M8 7h8M8 11h8M8 15h4" />
    </svg>
  );
}

function IconAudit({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className={className}>
      <path d="M12 3l8 4v6c0 5-3.5 7.5-8 9-4.5-1.5-8-4-8-9V7l8-4z" />
      <path d="M9 12l2 2 4-4" />
    </svg>
  );
}

function IconCompliance({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className={className}>
      <path d="M9 12l2 2 4-4" />
      <path d="M21 12c0 7-9 10-9 10S3 19 3 12V5l9-3 9 3v7Z" />
    </svg>
  );
}

function IconBilling({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className={className}>
      <rect x="4" y="3" width="16" height="18" rx="2" />
      <path d="M8 7h8M8 11h8M8 15h5" />
      <path d="M16 15v4M14 17h4" />
    </svg>
  );
}

function IconClock({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className={className}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 3" />
    </svg>
  );
}

function IconPayroll({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className={className}>
      <rect x="3" y="5" width="18" height="14" rx="2" />
      <path d="M3 10h18" />
      <path d="M7 15h3" />
      <path d="M14 15h4" />
    </svg>
  );
}

function IconAdmin({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className={className}>
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.2a1.7 1.7 0 0 0-1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.2a1.7 1.7 0 0 0 1.5-1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3h.1a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.2a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8v.1a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.2a1.7 1.7 0 0 0-1.4 1Z" />
    </svg>
  );
}

const navSections: NavSection[] = [
  {
    label: "Work",
    items: [
      { href: "/dashboard", label: "Operations", icon: IconGrid },
      { href: "/tasks", label: "Tasks", icon: IconTask },
      { href: "/calls-reception", label: "Calls & Reception", icon: IconPhone },
      { href: "/pipeline", label: "Pipeline", icon: IconPipeline },
    ],
  },
  {
    label: "People",
    items: [
      { href: "/clients", label: "Clients", icon: IconUsers },
      { href: "/staff", label: "Staff", icon: IconUserBadge },
    ],
  },
  {
    label: "Communication",
    items: [{ href: "/activity-log", label: "Activity Log", icon: IconActivity }],
  },
  {
    label: "Documents",
    items: [
      { href: "/documents", label: "Documents", icon: IconDocuments },
      { href: "/forms", label: "Forms", icon: IconForm },
    ],
  },
  {
    label: "Oversight",
    items: [
      { href: "/audit-center", label: "Audit Center", icon: IconAudit },
      { href: "/compliance", label: "Compliance", icon: IconCompliance },
      { href: "/billing", label: "Billing", icon: IconBilling },
    ],
  },
  {
    label: "Workforce",
    items: [
      { href: "/time-attendance", label: "Time & Attendance", icon: IconClock },
      { href: "https://tsheets.intuit.com/ip/#_SwitchJC", label: "Clock In/Out", icon: IconClock, external: true },
      { href: "/payroll", label: "Payroll", icon: IconPayroll },
      {
        href: "https://tsheets.intuit.com/",
        label: "QuickBooks Time (Managers)",
        icon: IconPayroll,
        external: true,
        visibleToRoles: ["admin", "office_manager", "supervisor", "sud_supervisor"],
      },
    ],
  },
  {
    label: "Admin",
    items: [{ href: "/admin-center", label: "Admin Center", icon: IconAdmin }],
  },
];

type SidebarProps = {
  role?: string | null;
};

function normalizeRole(role: string | null | undefined): string {
  return (role || "").trim().toLowerCase();
}

function isItemVisible(item: NavItem, role: string | null | undefined): boolean {
  if (!item.visibleToRoles || item.visibleToRoles.length === 0) return true;
  const normalizedRole = normalizeRole(role);
  return item.visibleToRoles.some((entry) => normalizeRole(entry) === normalizedRole);
}

export default function Sidebar({ role = null }: SidebarProps) {
  const pathname = usePathname();
  const normalizedRole = normalizeRole(role);

  return (
    <aside className="flex h-full min-h-0 flex-col gap-6 overflow-hidden rounded-xl border border-slate-900 bg-[var(--ui-nav-bg)] p-5 text-[var(--ui-nav-inactive-fg)] lg:sticky lg:top-6 lg:h-[calc(100vh-3rem)]">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-slate-800 text-[var(--ui-nav-active-fg)]">
          <IconPulse className="h-5 w-5" />
        </div>
        <div>
          <div className="text-lg font-semibold tracking-tight text-[var(--ui-nav-active-fg)]">{BRANDING.name}</div>
          <div className="text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-500">{BRANDING.tagline}</div>
        </div>
      </div>

      <nav className="min-h-0 flex-1 space-y-5 overflow-y-auto pr-1" aria-label="Primary navigation">
        {navSections.map((section) => (
          <div key={section.label} className="space-y-2">
            <p className="px-2 text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-500">{section.label}</p>
            <div className="space-y-1">
              {section.items.filter((item) => isItemVisible(item, normalizedRole)).map((item) => {
                const isInternal = item.href.startsWith("/");
                const isActive = isInternal && (pathname === item.href || pathname?.startsWith(`${item.href}/`));
                const Icon = item.icon;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    target={item.external ? "_blank" : undefined}
                    rel={item.external ? "noopener noreferrer" : undefined}
                    className={`group relative flex items-center gap-3 rounded-lg px-3 py-2.5 transition-colors duration-150 ${
                      isActive
                        ? "bg-[var(--ui-nav-active-bg)] text-[var(--ui-nav-active-fg)]"
                        : "bg-transparent text-[var(--ui-nav-inactive-fg)] hover:bg-[var(--ui-nav-hover-bg)]"
                    }`}
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
                    <span className={`text-sm font-semibold ${isActive ? "text-[var(--ui-nav-active-fg)]" : "text-[var(--ui-nav-inactive-fg)]"}`}>
                      {item.label}
                    </span>
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      <div className="mt-auto rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2.5 text-[10px] uppercase tracking-[0.2em] text-slate-500">
        {BRANDING.environmentLabel}
      </div>
    </aside>
  );
}
