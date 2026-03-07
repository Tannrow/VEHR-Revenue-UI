import Link from "next/link";

import { PageShell } from "@/components/page-shell";

export default function Home() {
  return (
    <PageShell
      title="VEHR Revenue OS"
      description="Command center for financial exposure, recovery, payer aggression, and claim execution."
      footer="Staging Environment · Azure Container Apps · PostgreSQL 15 · Deterministic Pipeline"
    >
      <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
        <Link
          href="/dashboard/"
          className="rounded-xl border border-zinc-800 bg-zinc-900 p-6 transition hover:border-white"
        >
          <h2 className="mb-2 text-xl font-semibold">
            Executive Dashboard
          </h2>
          <p className="text-zinc-400">
            Exposure, 30-day recovery forecast, payer aggression tiers.
          </p>
        </Link>

        <Link
          href="/era/"
          className="rounded-xl border border-zinc-800 bg-zinc-900 p-6 transition hover:border-white"
        >
          <h2 className="mb-2 text-xl font-semibold">
            ERA Intake
          </h2>
          <p className="text-zinc-400">
            Upload and process remittance files. Structured validation and ledger sync.
          </p>
        </Link>

        <Link
          href="/claims/"
          className="rounded-xl border border-zinc-800 bg-zinc-900 p-6 transition hover:border-white"
        >
          <h2 className="mb-2 text-xl font-semibold">
            Claims
          </h2>
          <p className="text-zinc-400">
            Track OPEN, PARTIAL, DENIED, and PAID claims with ledger status.
          </p>
        </Link>
      </div>
    </PageShell>
  );
}
