"use client";

import { PanelLeftClose, PanelLeftOpen } from "lucide-react";

import { SidebarNav, type SidebarNavGroup } from "@/components/enterprise/sidebar-nav";
import { Button } from "@/components/ui/button";

type ModuleSidebarProps = {
  moduleName: string;
  groups: SidebarNavGroup[];
  collapsed?: boolean;
  showCollapseToggle?: boolean;
  onToggleCollapsed?: () => void;
};

function shortLabel(value: string): string {
  const parts = value.trim().split(/\s+/).filter(Boolean);
  if (parts.length >= 2) {
    return `${parts[0].slice(0, 1)}${parts[1].slice(0, 1)}`.toUpperCase();
  }
  return value.slice(0, 2).toUpperCase();
}

export function ModuleSidebar({
  moduleName,
  groups,
  collapsed = false,
  showCollapseToggle = false,
  onToggleCollapsed,
}: ModuleSidebarProps) {
  return (
    <div className="space-y-[var(--space-12)]">
      <div className="ui-panel px-[var(--space-12)] py-[var(--space-12)]">
        <div className="flex items-center justify-between gap-[var(--space-8)]">
          <div className="min-w-0">
            <p className="text-[11px] font-medium text-[var(--neutral-muted)]">Navigation</p>
            <p className="ui-type-body mt-[var(--space-4)] truncate font-semibold text-[var(--neutral-text)]">
              {collapsed ? shortLabel(moduleName) : moduleName}
            </p>
          </div>
          {showCollapseToggle ? (
            <Button
              type="button"
              variant="ghost"
              size="icon"
              onClick={onToggleCollapsed}
              aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
              title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
              className="h-8 w-8 shrink-0"
            >
              {collapsed ? <PanelLeftOpen className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}
            </Button>
          ) : null}
        </div>
      </div>
      <SidebarNav groups={groups} collapsed={collapsed} />
    </div>
  );
}
