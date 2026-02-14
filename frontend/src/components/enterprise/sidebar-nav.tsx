import Link from "next/link";

import { cn } from "@/lib/utils";

export type SidebarNavItem = {
  id: string;
  label: string;
  description?: string;
  badge?: string;
  href?: string;
  active?: boolean;
  disabled?: boolean;
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
  className?: string;
  testId?: string;
};

function itemClasses(item: SidebarNavItem): string {
  const base =
    "group flex w-full items-start justify-between gap-[var(--space-8)] rounded-[var(--radius-6)] border px-[var(--space-12)] py-[var(--space-8)] text-left transition-colors";
  if (item.disabled) {
    return cn(base, "cursor-not-allowed border-[var(--neutral-border)] bg-[var(--neutral-panel)] opacity-60");
  }
  if (item.active) {
    return cn(
      base,
      "border-[var(--neutral-border)] bg-[var(--accent)] text-[var(--neutral-text)] shadow-[var(--shadow-1)]",
    );
  }
  return cn(
    base,
    "border-[var(--neutral-border)] bg-[var(--neutral-panel)] text-[var(--neutral-text)] hover:bg-[var(--muted)]",
  );
}

function SidebarNavEntry({ item }: { item: SidebarNavItem }) {
  const content = (
    <>
      <span className="min-w-0">
        <span className="block text-[length:var(--font-size-14)] font-semibold leading-tight">{item.label}</span>
        {item.description ? (
          <span className="mt-[var(--space-4)] block text-[length:var(--font-size-12)] text-[var(--neutral-muted)]">
            {item.description}
          </span>
        ) : null}
      </span>
      {item.badge ? (
        <span className="ui-status-pill ui-status-info mt-[2px] shrink-0 whitespace-nowrap">{item.badge}</span>
      ) : null}
    </>
  );

  if (item.href && !item.disabled) {
    return (
      <Link href={item.href} className={itemClasses(item)} data-testid={item.testId}>
        {content}
      </Link>
    );
  }

  return (
    <button
      type="button"
      className={itemClasses(item)}
      onClick={item.onSelect}
      disabled={item.disabled}
      data-testid={item.testId}
    >
      {content}
    </button>
  );
}

export function SidebarNav({ groups, className, testId }: SidebarNavProps) {
  return (
    <nav
      aria-label="Section navigation"
      className={cn("ui-panel flex flex-col gap-[var(--space-16)] p-[var(--space-16)]", className)}
      data-testid={testId}
    >
      {groups.map((group) => (
        <section key={group.id} className="space-y-[var(--space-8)]">
          <h2 className="ui-type-meta font-semibold uppercase tracking-[0.14em]">{group.label}</h2>
          <ul className="space-y-[var(--space-8)]">
            {group.items.map((item) => (
              <li key={item.id}>
                <SidebarNavEntry item={item} />
              </li>
            ))}
          </ul>
        </section>
      ))}
    </nav>
  );
}

