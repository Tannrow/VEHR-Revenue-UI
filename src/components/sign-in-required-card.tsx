import Link from "next/link";

import { SectionCard } from "@/components/page-shell";

type SignInRequiredCardProps = {
  resource: string;
};

export function SignInRequiredCard({ resource }: SignInRequiredCardProps) {
  return (
    <SectionCard title="Sign in required">
      <div className="space-y-4 text-sm text-zinc-300">
        <p>Sign in to access {resource}.</p>

        <div className="flex flex-wrap gap-3">
          <Link
            href="/login"
            className="inline-flex rounded-md border border-white px-4 py-2 font-medium text-white transition hover:bg-white hover:text-black"
          >
            Go to sign in
          </Link>

          <Link
            href="/"
            className="inline-flex rounded-md border border-zinc-700 px-4 py-2 text-white transition hover:border-white"
          >
            Back to home
          </Link>
        </div>
      </div>
    </SectionCard>
  );
}
