import type { ReactNode } from "react";
import Link from "next/link";

import { AppShell } from "@/components/revenue-os/app-shell";

type PageShellProps = {
  title: string;
  description?: string;
  children: ReactNode;
  footer?: ReactNode;
  eyebrow?: string;
  actions?: ReactNode;
};

export function PageShell({
  title,
  description,
  children,
  footer,
  eyebrow = "VEHR Revenue OS",
  actions,
}: PageShellProps) {
  return (
    <AppShell>
      <main className="min-h-screen">
        <div className="mx-auto max-w-[1600px] space-y-8 px-5 py-6 md:px-8">
          <header className="relative overflow-hidden rounded-[28px] border border-white/8 bg-[linear-gradient(180deg,rgba(22,26,35,0.96),rgba(16,19,27,0.98))] p-6 shadow-[0_24px_90px_rgba(0,0,0,0.36)] backdrop-blur-sm md:p-8">
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(255,255,255,0.04),transparent_32%),linear-gradient(180deg,rgba(255,255,255,0.01),transparent_55%)]" />
            <div className="relative flex flex-col gap-6 xl:flex-row xl:items-end xl:justify-between">
              <div className="max-w-4xl space-y-4">
                <p className="text-[11px] uppercase tracking-[0.34em] text-slate-500">{eyebrow}</p>
                <div className="space-y-3">
                  <h1 className="text-4xl font-semibold tracking-[-0.04em] text-white md:text-[3.25rem]">{title}</h1>
                  {description ? (
                    <p className="max-w-3xl text-base leading-7 text-slate-300 md:text-[1.05rem]">{description}</p>
                  ) : null}
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-3">
                {actions}
                <Link
                  href="/dashboard"
                  className="inline-flex items-center rounded-full border border-white/10 bg-white/[0.04] px-4 py-2 text-sm font-medium text-white hover:-translate-y-[1px] hover:border-white/18 hover:bg-white/[0.08]"
                >
                  Open Work Queue
                </Link>
              </div>
            </div>
          </header>

          <div className="space-y-6">{children}</div>

          {footer ? <footer className="border-t border-white/8 pt-5 text-sm text-slate-500">{footer}</footer> : null}
        </div>
      </main>
    </AppShell>
  );
}

type SectionCardProps = {
  title: string;
  children: ReactNode;
  subtitle?: string;
  actions?: ReactNode;
};

export function SectionCard({ title, children, subtitle, actions }: SectionCardProps) {
  return (
    <section className="rounded-[24px] border border-white/8 bg-[linear-gradient(180deg,rgba(20,24,33,0.94),rgba(17,20,28,0.96))] p-5 shadow-[0_18px_70px_rgba(0,0,0,0.22)] backdrop-blur-sm md:p-6">
      <div className="mb-5 flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div className="space-y-1">
          <h2 className="text-xl font-semibold tracking-[-0.02em] text-white">{title}</h2>
          {subtitle ? <p className="max-w-3xl text-sm text-slate-400">{subtitle}</p> : null}
        </div>
        {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
      </div>
      {children}
    </section>
  );
}
