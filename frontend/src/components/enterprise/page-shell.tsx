import { ReactNode } from "react";

import { cn } from "@/lib/utils";

type PageShellProps = {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: ReactNode;
  metrics?: ReactNode;
  sidebar?: ReactNode;
  children: ReactNode;
  className?: string;
  contentClassName?: string;
  testId?: string;
};

export function PageShell({
  eyebrow,
  title,
  description,
  actions,
  metrics,
  sidebar,
  children,
  className,
  contentClassName,
  testId,
}: PageShellProps) {
  return (
    <div className={cn("flex flex-col gap-[var(--space-24)]", className)} data-testid={testId}>
      <header className="flex flex-wrap items-start justify-between gap-[var(--space-16)]">
        <div className="min-w-0 space-y-[var(--space-8)]">
          {eyebrow ? (
            <p className="ui-type-meta font-semibold uppercase tracking-[0.14em]">{eyebrow}</p>
          ) : null}
          <h1 className="ui-type-page-title text-[var(--neutral-text)]">{title}</h1>
          {description ? (
            <p className="ui-type-body max-w-3xl text-[var(--neutral-muted)]">{description}</p>
          ) : null}
        </div>
        {actions ? <div className="flex flex-wrap items-center gap-[var(--space-8)]">{actions}</div> : null}
      </header>

      {metrics ? <div>{metrics}</div> : null}

      {sidebar ? (
        <div className={cn("grid gap-[var(--space-16)] xl:grid-cols-[280px_minmax(0,1fr)]", contentClassName)}>
          <aside>{sidebar}</aside>
          <section className="min-w-0">{children}</section>
        </div>
      ) : (
        <section className={cn("min-w-0", contentClassName)}>{children}</section>
      )}
    </div>
  );
}

