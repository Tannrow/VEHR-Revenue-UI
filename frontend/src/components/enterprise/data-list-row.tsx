import { ReactNode } from "react";

import { cn } from "@/lib/utils";

type StatusTone = "neutral" | "informational" | "stable" | "attention" | "critical";

type DataListRowProps = {
  title: ReactNode;
  description?: ReactNode;
  meta?: ReactNode | ReactNode[];
  statusLabel?: string;
  statusTone?: StatusTone;
  actions?: ReactNode;
  className?: string;
  onClick?: () => void;
  testId?: string;
};

const toneClass: Record<StatusTone, string> = {
  neutral: "border-[var(--neutral-border)] bg-[var(--neutral-panel)] text-[var(--neutral-muted)]",
  informational: "ui-status-info",
  stable: "ui-status-success",
  attention: "ui-status-warning",
  critical: "ui-status-error",
};

function normalizeMeta(meta: ReactNode | ReactNode[] | undefined): ReactNode[] {
  if (!meta) return [];
  return Array.isArray(meta) ? meta : [meta];
}

export function DataListRow({
  title,
  description,
  meta,
  statusLabel,
  statusTone = "neutral",
  actions,
  className,
  onClick,
  testId,
}: DataListRowProps) {
  const metaItems = normalizeMeta(meta);
  const Container: "button" | "div" = onClick ? "button" : "div";

  return (
    <Container
      type={onClick ? "button" : undefined}
      onClick={onClick}
      className={cn(
        "w-full rounded-[var(--radius-6)] border border-[var(--neutral-border)] bg-[var(--neutral-panel)] px-[var(--space-12)] py-[var(--space-12)] text-left",
        onClick
          ? "transition-colors duration-150 hover:bg-[var(--muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]"
          : "",
        className,
      )}
      data-testid={testId}
    >
      <div className="flex flex-wrap items-start justify-between gap-[var(--space-8)]">
        <div className="min-w-0 flex-1">
          <p className="text-[length:var(--font-size-14)] font-semibold text-[var(--neutral-text)]">{title}</p>
          {description ? (
            <p className="ui-type-body mt-[var(--space-4)] text-[var(--neutral-muted)]">{description}</p>
          ) : null}
          {metaItems.length > 0 ? (
            <div className="mt-[var(--space-4)] flex flex-wrap gap-x-[var(--space-12)] gap-y-[var(--space-4)]">
              {metaItems.map((item, idx) => (
                <span key={idx} className="ui-type-meta">
                  {item}
                </span>
              ))}
            </div>
          ) : null}
        </div>

        <div className="flex items-center gap-[var(--space-8)]">
          {statusLabel ? (
            <span className={cn("ui-status-pill", toneClass[statusTone])}>{statusLabel}</span>
          ) : null}
          {actions ? <div className="flex items-center gap-[var(--space-8)]">{actions}</div> : null}
        </div>
      </div>
    </Container>
  );
}

