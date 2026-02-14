import { ReactNode } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

type SectionCardProps = {
  title: string;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  contentClassName?: string;
  testId?: string;
};

export function SectionCard({
  title,
  description,
  actions,
  children,
  className,
  contentClassName,
  testId,
}: SectionCardProps) {
  return (
    <Card className={cn("bg-[var(--neutral-panel)] shadow-sm hover:shadow-md", className)} data-testid={testId}>
      <CardHeader className="border-b border-[var(--neutral-border)] pb-[var(--space-12)]">
        <div className="flex flex-wrap items-center justify-between gap-[var(--space-8)]">
          <CardTitle className="ui-type-section-title text-[var(--neutral-text)]">{title}</CardTitle>
          {actions ? <div className="flex flex-wrap items-center gap-[var(--space-8)]">{actions}</div> : null}
        </div>
        {description ? (
          <p className="ui-type-body text-[var(--neutral-muted)]">{description}</p>
        ) : null}
      </CardHeader>
      <CardContent className={cn("pt-[var(--space-16)]", contentClassName)}>{children}</CardContent>
    </Card>
  );
}
