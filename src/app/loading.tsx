import { PageShell, SectionCard } from "@/components/page-shell";

export default function Loading() {
  return (
    <PageShell
      title="Loading Revenue OS"
      description="Preparing the current route and resolving backend connectivity."
    >
      <SectionCard title="Please wait">
        <p className="text-sm text-zinc-300">The application is loading the latest route state.</p>
      </SectionCard>
    </PageShell>
  );
}
