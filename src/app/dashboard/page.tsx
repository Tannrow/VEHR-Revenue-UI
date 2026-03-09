import Link from "next/link";

import { PageShell, SectionCard } from "@/components/page-shell";

export default function DashboardPage() {
  return (
    <PageShell
      title="Dashboard"
      description="Staging dashboard UI is available without requiring live API data."
      footer="Staging UI · This page is safe to load before backend integrations are connected."
    >
      <SectionCard title="Revenue dashboard">
        <div className="space-y-4 text-sm text-zinc-300">
          <p>Use this staging surface to validate navigation and deployment health while live dashboard data is still being connected.</p>
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
