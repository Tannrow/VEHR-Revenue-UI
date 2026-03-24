"use client";

import { Suspense, type ReactNode } from "react";
import { useCallback, useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

const primaryNav = [
  { href: "/dashboard", label: "Work Queue", badge: "Today" },
  { href: "/claims", label: "Claims", badge: "Objects" },
  { href: "/era", label: "ERA Pipeline", badge: "Ingest" },
  { href: "/diagnostics", label: "Diagnostics", badge: "Ops" },
];

const secondaryNav = [
  { href: "/dashboard?panel=insights", label: "Insights" },
  { href: "/dashboard?panel=policy", label: "Policy Engine" },
];

function SecondaryNavItems({
  pathname,
  activePanel,
}: {
  pathname: string;
  activePanel: string | null;
}) {
  return secondaryNav.map((item) => (
    <Link
      key={item.href}
      href={item.href}
      className={`flex items-center justify-between rounded-2xl border px-3 py-3 text-sm ${
        pathname === "/dashboard" && activePanel && item.href.includes(activePanel)
          ? "border-white/8 bg-white/[0.06] text-white"
          : "border-transparent text-slate-400 hover:-translate-y-[1px] hover:border-white/6 hover:bg-white/[0.04] hover:text-white"
      }`}
    >
      <span>{item.label}</span>
    </Link>
  ));
}

function SecondaryNav({ pathname }: { pathname: string }) {
  const searchParams = useSearchParams();

  return <SecondaryNavItems pathname={pathname} activePanel={searchParams.get("panel")} />;
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [commandOpen, setCommandOpen] = useState(false);
  const [commandQuery, setCommandQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const deferredQuery = useDeferredValue(commandQuery);

  const commands = useMemo(
    () => [
      {
        id: "go-work-queue",
        label: "Open Work Queue",
        detail: "Jump back to the primary denial triage surface.",
        href: "/dashboard",
        kind: "Navigation",
      },
      {
        id: "go-policy-engine",
        label: "Open Policy Engine",
        detail: "Inspect routing logic and rule coverage.",
        href: "/dashboard?panel=policy",
        kind: "Panel",
      },
      {
        id: "go-insights",
        label: "Open Insights",
        detail: "Review operational signals and drill into the queue.",
        href: "/dashboard?panel=insights",
        kind: "Panel",
      },
      {
        id: "go-era",
        label: "Open ERA Pipeline",
        detail: "Move into remit intake and processing.",
        href: "/era",
        kind: "Navigation",
      },
      {
        id: "go-diagnostics",
        label: "Open Diagnostics",
        detail: "Check Azure, Postgres, and GitHub connector health.",
        href: "/diagnostics",
        kind: "Navigation",
      },
      {
        id: "view-critical-priority",
        label: "Show Critical Priority",
        detail: "Filter the live queue to the most urgent claims.",
        href: "/dashboard?priority=critical",
        kind: "View",
      },
      {
        id: "view-denied-claims",
        label: "Show Denied Claims",
        detail: "Filter the live queue to denied backend claims.",
        href: "/dashboard?queue=Denied+claims&status=blocked",
        kind: "View",
      },
      {
        id: "view-open-balances",
        label: "Show Open Balances",
        detail: "Review open and partial balances surfaced by the snapshot.",
        href: "/dashboard?queue=Open+balances",
        kind: "View",
      },
    ],
    [],
  );

  const filteredCommands = useMemo(() => {
    const normalizedQuery = deferredQuery.trim().toLowerCase();

    if (!normalizedQuery) {
      return commands.slice(0, 8);
    }

    return commands
      .filter((command) =>
        `${command.label} ${command.detail} ${command.kind}`.toLowerCase().includes(normalizedQuery),
      )
      .slice(0, 10);
  }, [commands, deferredQuery]);

  const openCommandPalette = useCallback(() => {
    setCommandQuery("");
    setActiveIndex(0);
    setCommandOpen(true);
  }, []);

  const runCommand = useCallback(
    (href: string) => {
      setCommandOpen(false);
      setCommandQuery("");
      setActiveIndex(0);
      router.push(href);
    },
    [router],
  );

  useEffect(() => {
    function handleKeydown(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      const isTypingSurface =
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        Boolean(target?.closest("[contenteditable='true']"));

      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        if (commandOpen) {
          setCommandOpen(false);
        } else {
          openCommandPalette();
        }
        return;
      }

      if (commandOpen) {
        if (event.key === "ArrowDown") {
          event.preventDefault();
          setActiveIndex((current) => (filteredCommands.length === 0 ? 0 : Math.min(current + 1, filteredCommands.length - 1)));
          return;
        }

        if (event.key === "ArrowUp") {
          event.preventDefault();
          setActiveIndex((current) => Math.max(current - 1, 0));
          return;
        }

        if (event.key === "Enter" && filteredCommands[activeIndex]) {
          event.preventDefault();
          runCommand(filteredCommands[activeIndex].href);
          return;
        }

        if (event.key === "Escape") {
          event.preventDefault();
          setCommandOpen(false);
        }
        return;
      }

      if (isTypingSurface) {
        return;
      }

      if (event.key === "?") {
        event.preventDefault();
        openCommandPalette();
        return;
      }

      if (!event.metaKey && !event.ctrlKey && !event.altKey) {
        if (event.key.toLowerCase() === "e") {
          event.preventDefault();
          router.push("/era");
          return;
        }

        if (event.key.toLowerCase() === "d") {
          event.preventDefault();
          router.push("/diagnostics");
          return;
        }

        if (event.key.toLowerCase() === "w") {
          event.preventDefault();
          router.push("/dashboard");
        }
      }
    }

    window.addEventListener("keydown", handleKeydown);
    return () => window.removeEventListener("keydown", handleKeydown);
  }, [activeIndex, commandOpen, filteredCommands, openCommandPalette, router, runCommand]);

  useEffect(() => {
    if (!commandOpen) {
      return;
    }

    const frame = window.requestAnimationFrame(() => inputRef.current?.focus());
    return () => window.cancelAnimationFrame(frame);
  }, [commandOpen]);

  const shortcuts = useMemo(
    () => [
      { keys: "⌘K", label: "Command menu" },
      { keys: "E", label: "Open ERA intake" },
      { keys: "D", label: "Open diagnostics" },
      { keys: "W", label: "Jump to queue" },
      { keys: "?", label: "Shortcut help" },
    ],
    [],
  );

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top,rgba(110,168,254,0.08),transparent_25%),#0e1117] text-white">
      <div className="sticky top-0 z-30 border-b border-white/6 bg-[rgba(14,17,23,0.82)] backdrop-blur-xl lg:hidden">
        <div className="flex items-center justify-between px-4 py-3">
          <div>
            <p className="text-[11px] uppercase tracking-[0.28em] text-slate-500">Revenue OS</p>
            <p className="text-sm font-semibold text-white">VEHR</p>
          </div>
          <button
            type="button"
            onClick={openCommandPalette}
            className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-2 text-sm text-slate-200"
          >
            ⌘K
          </button>
        </div>
        <div className="flex gap-2 overflow-x-auto px-4 pb-3">
          {primaryNav.map((item) => {
            const active = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`whitespace-nowrap rounded-full border px-3 py-2 text-sm ${
                  active
                    ? "border-white/12 bg-white/[0.1] text-white"
                    : "border-white/8 bg-white/[0.03] text-slate-300"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </div>
      </div>

      <div className="grid min-h-screen lg:grid-cols-[264px_minmax(0,1fr)]">
        <aside className="hidden border-r border-white/6 bg-[linear-gradient(180deg,rgba(14,17,23,0.96),rgba(12,14,20,0.98))] lg:block">
          <div className="flex h-full flex-col px-4 py-5">
            <div className="space-y-5">
              <div className="space-y-3">
                <div className="inline-flex items-center rounded-full border border-white/8 bg-white/[0.03] px-3 py-1 text-[11px] uppercase tracking-[0.28em] text-slate-400">
                  Revenue OS
                </div>
                <div>
                  <h2 className="text-xl font-semibold tracking-[-0.03em] text-white">VEHR</h2>
                  <p className="mt-1 text-sm leading-6 text-slate-400">Workflow-first recovery system for claims, denials, and remits.</p>
                </div>
              </div>

              <button
                type="button"
                onClick={openCommandPalette}
                className="flex w-full items-center justify-between rounded-2xl border border-white/8 bg-white/[0.035] px-4 py-3 text-left text-sm text-slate-300 hover:-translate-y-[1px] hover:border-white/14 hover:bg-white/[0.05]"
              >
                <span>Search or run</span>
                <span className="rounded-md border border-white/10 px-2 py-0.5 text-xs text-slate-400">⌘K</span>
              </button>
            </div>

            <nav className="mt-7 space-y-6">
              <div className="space-y-2">
                <p className="px-3 text-[11px] uppercase tracking-[0.28em] text-slate-500">Operate</p>
                {primaryNav.map((item) => {
                  const active = pathname === item.href;
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      className={`flex items-center justify-between rounded-2xl px-3 py-3 text-sm ${
                        active
                          ? "border border-white/8 bg-white/[0.07] text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]"
                          : "border border-transparent text-slate-300 hover:-translate-y-[1px] hover:border-white/6 hover:bg-white/[0.04] hover:text-white"
                      }`}
                    >
                      <span className="font-medium">{item.label}</span>
                      <span className={`rounded-full px-2 py-1 text-[10px] uppercase tracking-[0.22em] ${active ? "bg-white/8 text-slate-300" : "bg-white/[0.04] text-slate-500"}`}>
                        {item.badge}
                      </span>
                    </Link>
                  );
                })}
              </div>

              <div className="space-y-2">
                <p className="px-3 text-[11px] uppercase tracking-[0.28em] text-slate-500">Control</p>
                <Suspense fallback={<SecondaryNavItems pathname={pathname} activePanel={null} />}>
                  <SecondaryNav pathname={pathname} />
                </Suspense>
              </div>
            </nav>

            <div className="mt-auto space-y-3">
              <div className="rounded-[22px] border border-white/8 bg-white/[0.03] p-4 backdrop-blur-sm">
                <p className="text-[11px] uppercase tracking-[0.28em] text-slate-500">Pinned workflow</p>
                <p className="mt-3 text-sm font-medium text-white">Live queue views</p>
                <p className="mt-1 text-sm text-slate-400">Use filters or the command palette to jump into critical claims, denied work, and open balances.</p>
              </div>

              <div className="rounded-[22px] border border-white/8 bg-black/20 p-4 backdrop-blur-sm">
                <p className="text-[11px] uppercase tracking-[0.28em] text-slate-500">Shortcuts</p>
                <div className="mt-3 space-y-2">
                  {shortcuts.map((shortcut) => (
                    <div key={shortcut.keys} className="flex items-center justify-between text-sm text-slate-300">
                      <span>{shortcut.label}</span>
                      <span className="rounded-md border border-white/8 px-2 py-0.5 text-xs text-slate-500">{shortcut.keys}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </aside>

        <div className="min-w-0">{children}</div>
      </div>

      {commandOpen ? (
        <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 px-4 pt-20 backdrop-blur-sm" onClick={() => setCommandOpen(false)}>
          <div
            className="w-full max-w-2xl overflow-hidden rounded-[28px] border border-white/10 bg-[linear-gradient(180deg,rgba(20,24,33,0.96),rgba(15,18,25,0.96))] shadow-[0_30px_120px_rgba(0,0,0,0.6)]"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="border-b border-white/8 px-5 py-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-xs uppercase tracking-[0.28em] text-slate-500">Command palette</p>
                  <h3 className="mt-1 text-lg font-semibold text-white">Jump, filter, and act without leaving the queue</h3>
                </div>
                <button
                  type="button"
                  onClick={() => setCommandOpen(false)}
                  className="rounded-full border border-white/10 px-3 py-1 text-sm text-slate-400 transition hover:border-white/20 hover:text-white"
                >
                  Esc
                </button>
              </div>
              <div className="mt-4 rounded-2xl border border-white/8 bg-black/25 px-4 py-3">
                <input
                  ref={inputRef}
                  value={commandQuery}
                  onChange={(event) => {
                    setCommandQuery(event.target.value);
                    setActiveIndex(0);
                  }}
                  placeholder="Search views, queues, statuses, or actions"
                  className="w-full bg-transparent text-sm text-slate-200 outline-none placeholder:text-slate-500"
                />
              </div>
            </div>
            <div className="p-4">
              <div className="space-y-2">
                {filteredCommands.map((command, index) => (
                  <button
                    key={command.id}
                    type="button"
                    onClick={() => runCommand(command.href)}
                    className={`flex w-full items-center justify-between rounded-2xl border px-4 py-3 text-left text-sm ${
                      index === activeIndex
                        ? "border-white/10 bg-white/[0.06] text-white"
                        : "border-transparent text-slate-200 hover:border-white/8 hover:bg-white/[0.04]"
                    }`}
                  >
                    <div className="min-w-0">
                      <p className="truncate">{command.label}</p>
                      <p className="mt-1 truncate text-xs text-slate-500">{command.detail}</p>
                    </div>
                    <span className="rounded-full border border-white/8 px-2 py-1 text-[10px] uppercase tracking-[0.22em] text-slate-400">
                      {command.kind}
                    </span>
                  </button>
                ))}
                {filteredCommands.length === 0 ? (
                  <div className="rounded-2xl border border-dashed border-white/8 px-4 py-6 text-sm text-slate-400">
                    No matching commands. Try a claim ID, payer, queue, or action keyword.
                  </div>
                ) : null}
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
