import type { ReactNode } from "react";
import Link from "next/link";

import { cn } from "@/lib/utils";

export type SidebarNavItem = {
  id: string;
  label: string;
  description?: string;
  badge?: string;
  href?: string;
  external?: boolean;
  active?: boolean;
  disabled?: boolean;
  icon?: ReactNode;
  onSelect?: () => void;
  testId?: string;
};

export type SidebarNavGroup = {
  id: string;
  label: string;
  items: SidebarNavItem[];
};

type SidebarNavProps = {
  groups: SidebarNavGroup[];
  collapsed?: boolean;
  className?: string;
  testId?: string;
};

function normalizeGroupLabel(label: string): string {
  const normalized = label.replace(/[_-]+/g, " ").trim().toLowerCase();
  if (!normalized) {
    return "Section";
  }
  return `${normalized.slice(0, 1).toUpperCase()}${normalized.slice(1)}`;
}

function iconToken(label: string): string {
  const first = label.replace(/[^a-zA-Z0-9]/g, "").slice(0, 1);
  return first ? first.toUpperCase() : "N";
}

function iconClasses(item: SidebarNavItem): string {
  const base =
    "inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-[var(--radius-6)] border text-[10px] font-semibold transition-colors";

  if (item.disabled) {
    return cn(base, "border-[var(--neutral-border)] bg-[var(--neutral-panel)] text-[var(--neutral-muted)]");
  }

  if (item.active) {
    return cn(
      base,
      "border-[color-mix(in_srgb,var(--primary)_28%,white)] bg-[color-mix(in_srgb,var(--primary)_16%,white)] text-[var(--primary)]",
    );
  }

  return cn(
    base,
    "border-[var(--neutral-border)] bg-[var(--neutral-panel)] text-[var(--neutral-muted)] group-hover:border-[color-mix(in_srgb,var(--primary)_20%,white)] group-hover:text-[var(--primary)]",
  );
}

function itemClasses(item: SidebarNavItem, collapsed: boolean): string {
  const base =
    "group relative flex min-h-[44px] w-full items-center justify-between gap-[var(--space-8)] rounded-[var(--radius-8)] border border-transparent px-[var(--space-8)] py-[var(--space-8)] text-left transition-colors duration-150";
  const collapseClasses = collapsed ? "justify-center px-[var(--space-4)]" : "";

  if (item.disabled) {
    return cn(
      base,
      collapseClasses,
      "cursor-not-allowed text-[var(--neutral-muted)] opacity-60",
    );
  }

  if (item.active) {
    return cn(
      base,
      collapseClasses,
      "bg-[color-mix(in_srgb,var(--primary)_10%,var(--neutral-panel))] text-[var(--neutral-text)] shadow-[var(--shadow-1)] before:absolute before:inset-y-[8px] before:left-[2px] before:w-[3px] before:rounded-full before:bg-[var(--primary)]",
    );
  }

  return cn(
    base,
    collapseClasses,
    "text-[var(--neutral-text)] hover:bg-[var(--muted)]",
  );
}

function SidebarNavEntry({ item, collapsed }: { item: SidebarNavItem; collapsed: boolean }) {
  const title = collapsed ? item.label : undefined;

  const content = (
    <>
      <span className={cn("flex min-w-0 items-center gap-[var(--space-8)]", collapsed && "justify-center")}>
        <span className={iconClasses(item)} aria-hidden="true">
          {item.icon ?? iconToken(item.label)}
        </span>
        {!collapsed ? (
          <span className="min-w-0">
            <span className="block text-[length:var(--font-size-14)] font-semibold leading-tight">{item.label}</span>
            {item.description ? (
              <span className="mt-[2px] block text-[length:var(--font-size-12)] text-[var(--neutral-muted)]">
                {item.description}
              </span>
            ) : null}
          </span>
        ) : null}
      </span>

      {!collapsed && item.badge ? (
        <span className="ui-status-pill ui-status-info mt-[2px] shrink-0 whitespace-nowrap">{item.badge}</span>
      ) : null}
    </>
  );

  if (item.href && !item.disabled) {
    return (
      <Link
        href={item.href}
        target={item.external ? "_blank" : undefined}
        rel={item.external ? "noopener noreferrer" : undefined}
        className={itemClasses(item, collapsed)}
        data-testid={item.testId}
        title={title}
        aria-label={item.label}
        aria-current={item.active ? "page" : undefined}
      >
        {content}
      </Link>
    );
  }

  return (
    <button
      type="button"
      className={itemClasses(item, collapsed)}
      onClick={item.onSelect}
      disabled={item.disabled}
      data-testid={item.testId}
      title={title}
      aria-label={item.label}
      aria-current={item.active ? "page" : undefined}
    >
      {content}
    </button>
  );
}

export function SidebarNav({ groups, collapsed = false, className, testId }: SidebarNavProps) {
  return (
    <nav
      aria-label="Section navigation"
      className={cn(
        "ui-panel flex flex-col gap-[var(--space-12)] p-[var(--space-12)]",
        collapsed && "items-center p-[var(--space-8)]",
        className,
      )}
      data-testid={testId}
      data-collapsed={collapsed ? "true" : "false"}
    >
      {groups
        .filter((group) => group.items.length > 0)
        .map((group, index) => (
          <section
            key={group.id}
            className={cn(
              "w-full space-y-[var(--space-8)]",
              index > 0 && "border-t border-[var(--neutral-border)] pt-[var(--space-12)]",
              collapsed && "space-y-[var(--space-6)]",
            )}
          >
            <h2 className={cn("px-[var(--space-8)] text-[11px] font-medium text-[var(--neutral-muted)]", collapsed && "sr-only")}>
              {normalizeGroupLabel(group.label)}
            </h2>
            <ul className="space-y-[var(--space-4)]">
              {group.items.map((item) => (
                <li key={item.id}>
                  <SidebarNavEntry item={item} collapsed={collapsed} />
                </li>
              ))}
            </ul>
          </section>
        ))}
    </nav>
  );
}
