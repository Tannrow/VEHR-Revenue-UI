import Link from "next/link";

import { PageShell, SectionCard } from "@/components/page-shell";

export default function EraPage() {
  return (
    <PageShell
      title="ERA Intake"
      description="Staging ERA intake UI is available without requiring live remittance uploads."
      footer="Staging UI · This page is safe to load while backend ERA services are unavailable."
    >
      <SectionCard title="ERA intake">
        <div className="space-y-4 text-sm text-zinc-300">
          <p>Use this route to verify the staging shell for remittance intake before upload and processing integrations are enabled.</p>
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
