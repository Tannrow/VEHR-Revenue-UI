import { PageShell, SectionCard } from "@/components/page-shell";

export default function EraPage() {
  return (
    <PageShell
      title="ERA Intake"
      description="ERA intake UI shell is online. Connect this route to the authenticated upload and processing workflow."
      footer="Staging UI · This route stays available while API-backed ERA processing is offline."
    >
      <SectionCard title="Framework readiness">
        <ul className="space-y-2 text-sm text-zinc-300">
          <li>Environment validation now fails fast when backend URLs are malformed.</li>
          <li>The app exposes a first-party health endpoint at <span className="font-mono">/api/health</span> for monitoring and internal checks.</li>
          <li>CI can now validate linting, type safety, and production builds before deployment.</li>
        </ul>
      </SectionCard>
    </PageShell>
  );
}
