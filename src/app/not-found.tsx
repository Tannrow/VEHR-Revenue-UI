import Link from "next/link";

import { PageShell, SectionCard } from "@/components/page-shell";

export default function NotFound() {
  return (
    <PageShell
      title="Page not found"
      description="The route you requested does not exist in the current Revenue OS UI shell."
    >
      <SectionCard title="Next steps">
        <div className="space-y-4 text-sm text-zinc-300">
          <p>Return to the main workspace to choose one of the available product surfaces.</p>
          <Link
            href="/"
            className="inline-flex rounded-md border border-zinc-700 px-4 py-2 text-white transition hover:border-white"
          >
            Go to home
          </Link>
        </div>
      </SectionCard>
    </PageShell>
  );
}
