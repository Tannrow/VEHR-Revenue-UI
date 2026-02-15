"use client";

import { useEffect } from "react";

import { Button } from "@/components/ui/button";

type AnalyticsErrorPageProps = {
  error: Error & { digest?: string };
  reset: () => void;
};

export default function AnalyticsErrorPage({ error, reset }: AnalyticsErrorPageProps) {
  useEffect(() => {
    console.error("Analytics route crashed", error);
  }, [error]);

  return (
    <div className="rounded-[var(--radius-card)] border border-[color-mix(in_srgb,var(--status-critical)_30%,white)] bg-[color-mix(in_srgb,var(--status-critical)_8%,white)] p-[var(--space-16)] shadow-[var(--shadow)]">
      <h2 className="text-xl font-semibold text-[var(--status-critical)]">Analytics failed to load</h2>
      <p className="mt-[var(--space-8)] text-sm text-[var(--status-critical)]">
        The report encountered an unexpected client error. Retry to reload the analytics view.
      </p>
      <div className="mt-[var(--space-12)]">
        <Button type="button" variant="outline" onClick={() => reset()}>
          Retry
        </Button>
      </div>
    </div>
  );
}

