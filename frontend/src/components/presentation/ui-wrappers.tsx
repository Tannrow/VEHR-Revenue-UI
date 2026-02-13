import * as React from "react";

import { Badge, type BadgeProps } from "@/components/ui/badge";
import { Button, type ButtonProps } from "@/components/ui/button";
import { Table } from "@/components/ui/table";
import { cn } from "@/lib/utils";

type PanelUIProps = React.HTMLAttributes<HTMLDivElement>;
type TableUIProps = React.HTMLAttributes<HTMLTableElement>;

export const ButtonUI = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, ...props }, ref) => (
    <Button ref={ref} className={cn("ui-button", className)} {...props} />
  ),
);
ButtonUI.displayName = "ButtonUI";

export const PanelUI = React.forwardRef<HTMLDivElement, PanelUIProps>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn("ui-panel p-[var(--space-16)]", className)}
      {...props}
    />
  ),
);
PanelUI.displayName = "PanelUI";

export function BadgeUI({ className, ...props }: BadgeProps) {
  return <Badge className={cn("ui-badge", className)} {...props} />;
}

export const TableUI = React.forwardRef<HTMLTableElement, TableUIProps>(
  ({ className, ...props }, ref) => (
    <Table ref={ref} className={cn("ui-table", className)} {...props} />
  ),
);
TableUI.displayName = "TableUI";
