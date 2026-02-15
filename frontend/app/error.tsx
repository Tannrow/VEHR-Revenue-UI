"use client";

import { useEffect } from "react";

import { Button } from "@/components/ui/button";

type GlobalErrorPageProps = {
  error: Error & { digest?: string };
  reset: () => void;
};

export default function GlobalErrorPage({ error, reset }: GlobalErrorPageProps) {
  useEffect(() => {
    console.error("App-level route crash", error);
  }, [error]);

  return (
    <main className="flex min-h-screen items-center justify-center bg-background px-6 py-12">
      <div className="w-full max-w-xl rounded-[var(--radius-card)] border border-[color-mix(in_srgb,var(--status-critical)_30%,white)] bg-[color-mix(in_srgb,var(--status-critical)_8%,white)] p-[var(--space-16)] shadow-[var(--shadow)]">
        <h1 className="text-2xl font-semibold text-[var(--status-critical)]">Something went wrong</h1>
        <p className="mt-[var(--space-8)] text-sm text-[var(--status-critical)]">
          An unexpected client error occurred while loading this page. Try again.
        </p>
        <div className="mt-[var(--space-12)]">
          <Button type="button" variant="outline" onClick={() => reset()}>
            Retry
          </Button>
        </div>
      </div>
    </main>
  );
}

