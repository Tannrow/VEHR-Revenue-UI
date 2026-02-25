export default function Home() {
  return (
    <main className="min-h-screen bg-black text-white p-12">
      <div className="max-w-6xl mx-auto">
        <h1 className="text-4xl font-bold mb-2">
          VEHR Revenue OS
        </h1>
        <p className="text-zinc-400 mb-10">
          Command center for financial exposure, recovery, payer aggression, and claim execution.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">

          <a
            href="/dashboard"
            className="bg-zinc-900 p-6 rounded-xl border border-zinc-800 hover:border-white transition"
          >
            <h2 className="text-xl font-semibold mb-2">
              Executive Dashboard
            </h2>
            <p className="text-zinc-400">
              Exposure, 30-day recovery forecast, payer aggression tiers.
            </p>
          </a>

          <a
            href="/era"
            className="bg-zinc-900 p-6 rounded-xl border border-zinc-800 hover:border-white transition"
          >
            <h2 className="text-xl font-semibold mb-2">
              ERA Intake
            </h2>
            <p className="text-zinc-400">
              Upload and process remittance files. Structured validation and ledger sync.
            </p>
          </a>

          <a
            href="/claims"
            className="bg-zinc-900 p-6 rounded-xl border border-zinc-800 hover:border-white transition"
          >
            <h2 className="text-xl font-semibold mb-2">
              Claims
            </h2>
            <p className="text-zinc-400">
              Track OPEN, PARTIAL, DENIED, and PAID claims with ledger status.
            </p>
          </a>

        </div>

        <div className="mt-16 border-t border-zinc-800 pt-8 text-sm text-zinc-500">
          Staging Environment · Azure Container Apps · PostgreSQL 15 · Deterministic Pipeline
        </div>
      </div>
    </main>
  );
}
