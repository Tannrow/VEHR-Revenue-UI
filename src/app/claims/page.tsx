import Link from "next/link";

import { PageShell, SectionCard } from "@/components/page-shell";

export default function ClaimsPage() {
  return (
    <PageShell
      title="Claims"
      description="Staging claims UI is available without requiring live claim status data."
      footer="Staging UI · This page is safe to load while backend claims APIs are unavailable."
    >
      <SectionCard title="Claims workspace">
        <div className="space-y-4 text-sm text-zinc-300">
          <p>Use this route to verify the claims workspace shell before claim tracking and ledger integrations are enabled.</p>
          <Link
            href="/"
            className="inline-flex rounded-md border border-zinc-700 px-4 py-2 text-white transition hover:border-white"
          >
            Back to home
          </Link>
        </div>
      </SectionCard>
    </PageShell>
  );
}
