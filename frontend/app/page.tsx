export default function Home() {
  return (
    <main className="min-h-screen bg-black text-white p-12">
      <h1 className="text-4xl font-bold mb-6">
        Revenue OS – Command Center
      </h1>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <a
          href="/dashboard"
          className="bg-zinc-900 p-6 rounded-xl border border-zinc-800 hover:border-white transition"
        >
          <h2 className="text-xl font-semibold mb-2">Executive Dashboard</h2>
          <p className="text-zinc-400">
            Financial exposure, recovery projections, payer aggression.
          </p>
        </a>

        <a
          href="/era"
          className="bg-zinc-900 p-6 rounded-xl border border-zinc-800 hover:border-white transition"
        >
          <h2 className="text-xl font-semibold mb-2">ERA Intake</h2>
          <p className="text-zinc-400">
            Upload and process remittance files.
          </p>
        </a>

        <a
          href="/claims"
          className="bg-zinc-900 p-6 rounded-xl border border-zinc-800 hover:border-white transition"
        >
          <h2 className="text-xl font-semibold mb-2">Claims</h2>
          <p className="text-zinc-400">
            Track open, denied, partial, and paid claims.
          </p>
        </a>
      </div>
    </main>
  );
}
