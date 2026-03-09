import { PageShell, SectionCard } from "@/components/page-shell";

export default function ClaimsPage() {
  return (
    <PageShell
      title="Claims"
      description="Claims workspace shell is online. Integrate this route with org-scoped claim status and ledger timelines."
      footer="Staging UI · This route stays available without claim data from the backend."
    >
      <SectionCard title="Framework readiness">
        <ul className="space-y-2 text-sm text-zinc-300">
          <li>Shared page shell keeps the route layout consistent across product surfaces.</li>
          <li>Route-level loading, error, and not-found experiences are now defined at the app level.</li>
          <li>Use the typed backend helpers in <span className="font-mono">src/lib/backend.ts</span> for future claims integrations.</li>
        </ul>
      </SectionCard>
    </PageShell>
  );
}
