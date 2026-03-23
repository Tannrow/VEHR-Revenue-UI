import Link from "next/link";

import { PageShell } from "@/components/page-shell";

export default function Home() {
  return (
    <PageShell
      title="VEHR Revenue OS"
      description="Command center for financial exposure, recovery, payer aggression, and claim execution."
      footer="Staging Environment · Azure Container Apps · PostgreSQL 15 · Deterministic Pipeline"
    >
      <div>
        <div className="flex flex-wrap gap-3">
          <Link
            href="/login"
            className="inline-flex rounded-md border border-white px-4 py-2 font-medium text-white transition hover:bg-white hover:text-black"
          >
            Sign in
          </Link>
          <Link
            href="/diagnostics"
            className="inline-flex rounded-md border border-zinc-700 px-4 py-2 font-medium text-white transition hover:border-white"
          >
            Diagnostics
          </Link>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2 xl:grid-cols-4">
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

        <Link
          href="/diagnostics/"
          className="rounded-xl border border-sky-900/60 bg-[linear-gradient(180deg,rgba(8,47,73,0.95),rgba(9,9,11,0.95))] p-6 transition hover:border-sky-300"
        >
          <h2 className="mb-2 text-xl font-semibold">
            Environment Diagnostics
          </h2>
          <p className="text-sky-100/80">
            Live Azure, Postgres, and GitHub MCP health with same-origin checks through the UI.
          </p>
        </Link>
      </div>
    </PageShell>
  );
}
