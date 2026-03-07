"use client";

import { PageShell, SectionCard } from "@/components/page-shell";

type ErrorPageProps = {
  error: Error & { digest?: string };
  reset: () => void;
};

export default function ErrorPage({ error, reset }: ErrorPageProps) {
  return (
    <PageShell
      title="Something went wrong"
      description="The Revenue OS UI hit an unexpected application error."
      footer="Use the reset action below to retry the route. If the issue persists, review the server logs and backend connectivity."
    >
      <SectionCard title="Failure details">
        <div className="space-y-4 text-sm text-zinc-300">
          <p>{error.message || "Unknown application error."}</p>
          <button
            type="button"
            onClick={() => reset()}
            className="rounded-md border border-zinc-700 px-4 py-2 text-white transition hover:border-white"
          >
            Try again
          </button>
        </div>
      </SectionCard>
    </PageShell>
  );
}
