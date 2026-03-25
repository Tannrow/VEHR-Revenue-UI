import Link from "next/link";

import { PageShell, SectionCard } from "@/components/page-shell";
import { SignInRequiredCard } from "@/components/sign-in-required-card";
import { getAccessToken } from "@/lib/auth";

import { EraLabPanel } from "./era-lab-panel";

export const dynamic = "force-dynamic";

type PageProps = {
  params: Promise<{
    eraFileId: string;
  }>;
};

export default async function EraLabPage({ params }: PageProps) {
  const { eraFileId } = await params;
  const accessToken = await getAccessToken();

  if (!accessToken) {
    return (
      <PageShell
        title="ERA Replay Lab"
        description="Inspect redacted extraction previews, hybrid merge evidence, and replay selected stages without mutating persisted rows."
        footer={`ERA lab routes through /api/era/${eraFileId}/lab and /api/era/${eraFileId}/replay via the UI origin.`}
        actions={
          <Link
            href="/era"
            className="inline-flex items-center rounded-full border border-white/10 bg-white/[0.04] px-4 py-2 text-sm font-medium text-white hover:-translate-y-[1px] hover:border-white/18 hover:bg-white/[0.08]"
          >
            Back to uploads
          </Link>
        }
      >
        <SignInRequiredCard resource="ERA replay lab" />
      </PageShell>
    );
  }

  return (
    <PageShell
      title="ERA Replay Lab"
      description="Inspect redacted extraction previews, hybrid merge evidence, and replay selected stages without mutating persisted rows."
      footer={`ERA lab routes through /api/era/${eraFileId}/lab and /api/era/${eraFileId}/replay via the UI origin.`}
      actions={
        <Link
          href="/era"
          className="inline-flex items-center rounded-full border border-white/10 bg-white/[0.04] px-4 py-2 text-sm font-medium text-white hover:-translate-y-[1px] hover:border-white/18 hover:bg-white/[0.08]"
        >
          Back to uploads
        </Link>
      }
    >
      <SectionCard
        title={`ERA file ${eraFileId}`}
        subtitle="The lab is file-specific: use it to inspect the persisted snapshot, compare replay previews, and understand exactly why a file finalized or stayed review-required."
      >
        <EraLabPanel eraFileId={eraFileId} />
      </SectionCard>
    </PageShell>
  );
}
