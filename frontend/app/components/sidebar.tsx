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

function IconReferrals({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className={className}>
      <path d="M7 17l10-10" />
      <path d="M9 7h8v8" />
      <path d="M4 12v7h7" />
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

function IconReports({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className={className}>
      <path d="M4 4v16h16" />
      <path d="M8 14l3-3 3 2 4-5" />
    </svg>
  );
}

const navItems: NavItem[] = [
  {
    href: "/dashboard",
    label: "Operations",
    description: "CRM command center",
    icon: IconGrid,
  },
  {
    href: "/tasks",
    label: "Tasks",
    description: "Action queue",
    icon: IconTask,
  },
  {
    href: "/clients",
    label: "Clients",
    description: "Relationship records",
    icon: IconUsers,
  },
  {
    href: "/referrals",
    label: "Referrals / Prospects",
    description: "Pipeline and intake",
    icon: IconReferrals,
  },
  {
    href: "/documents",
    label: "Documents",
    description: "Internal resources & policies",
    icon: IconDocuments,
  },
  {
    href: "/reports",
    label: "Reports",
    description: "Operational insights",
    icon: IconReports,
  },
];

type SidebarProps = {
  role?: string | null;
};

export default function Sidebar({ role = null }: SidebarProps) {
  const pathname = usePathname();
  void role;

  return (
    <aside className="flex h-full min-h-0 flex-col gap-7 overflow-hidden rounded-xl border border-slate-900 bg-[var(--ui-nav-bg)] p-5 text-[var(--ui-nav-inactive-fg)] lg:sticky lg:top-6 lg:h-[calc(100vh-3rem)]">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-slate-800 text-[var(--ui-nav-active-fg)]">
          <IconPulse className="h-5 w-5" />
        </div>
        <div>
          <div className="text-lg font-semibold tracking-tight text-[var(--ui-nav-active-fg)]">{BRANDING.name}</div>
          <div className="text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-500">{BRANDING.tagline}</div>
        </div>
      </div>

      <nav className="min-h-0 flex-1 space-y-2 overflow-y-auto pr-1" aria-label="Primary navigation">
        {navItems.map((item) => {
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
      </nav>

      <div className="mt-auto space-y-3 text-xs text-slate-400">
        <div className="rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2.5">
          <div className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-400">
            <span className="h-2 w-2 rounded-full bg-[var(--ui-status-success)]" />
            {BRANDING.environmentLabel}
          </div>
          <p className="mt-2 text-[11px] text-slate-500">Operational workspace online.</p>
        </div>
        <div className="text-[10px] text-slate-500">{BRANDING.internalNote}</div>
      </div>
    </aside>
  );
}
