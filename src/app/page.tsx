import Link from "next/link";
import { redirect } from "next/navigation";

import { PageShell, SectionCard } from "@/components/page-shell";
import { getAccessToken } from "@/lib/auth";

export default async function Home() {
  const accessToken = await getAccessToken();

  if (accessToken) {
    redirect("/dashboard");
  }

  return (
    <PageShell
      eyebrow="Revenue operating system"
      title="Workflow-first recovery for claims, denials, and remit execution."
      description="Built around one primary work queue, one connected object model, and one quiet AI sidecar. The goal is operational clarity, not visual noise."
      footer="Linear-style workflow discipline · Stripe-inspired data clarity · subtle Vercel and Mercury polish"
      actions={
        <>
          <Link
            href="/login"
            className="inline-flex items-center rounded-full border border-white/10 bg-white/[0.04] px-4 py-2 text-sm font-medium text-white hover:-translate-y-[1px] hover:border-white/18 hover:bg-white/[0.08]"
          >
            Sign in
          </Link>
          <Link
            href="/dashboard"
            className="inline-flex items-center rounded-full border border-white/10 bg-white/[0.04] px-4 py-2 text-sm font-medium text-white hover:-translate-y-[1px] hover:border-white/18 hover:bg-white/[0.08]"
          >
            Launch queue
          </Link>
        </>
      }
    >
      <div className="grid gap-6 xl:grid-cols-[1.35fr_0.65fr]">
        <SectionCard
          title="Product north star"
          subtitle="The home screen is not a dashboard. It is a decision surface: intake, drill-down, evidence, action."
        >
          <div className="grid gap-4 md:grid-cols-2">
            {[
              {
                title: "Work Queue",
                body: "Linear-style triage for denial, authorization, and underpayment work with persistent filters, SLAs, and bulk actions.",
              },
              {
                title: "Claim Drawer",
                body: "Object-first detail view for claim, denial, encounter, patient, payer, authorization, documents, and timeline without leaving context.",
              },
              {
                title: "AI Sidecar",
                body: "Explain, recommend, and draft with evidence. AI never acts without confirmation and never hides its reasoning.",
              },
              {
                title: "Insights → Action",
                body: "Mercury-style metric storytelling and Palantir-like drill-down that always lands in a real queue with a real next step.",
              },
            ].map((item) => (
              <div key={item.title} className="rounded-[22px] border border-white/8 bg-white/[0.03] p-4 backdrop-blur-sm">
                <h3 className="text-lg font-semibold text-white">{item.title}</h3>
                <p className="mt-2 text-sm leading-6 text-slate-300">{item.body}</p>
              </div>
            ))}
          </div>
        </SectionCard>

        <SectionCard title="Open the system" subtitle="Use the live routes below to move through the operating model.">
          <div className="space-y-3">
            {[
              { href: "/dashboard", label: "Work Queue", body: "Primary operator cockpit with drawer + AI sidecar." },
              { href: "/claims", label: "Claims Objects", body: "Claim-centric drill-down surface and record inspection." },
              { href: "/era", label: "ERA Pipeline", body: "Remit intake with review summary and work-item generation." },
              { href: "/diagnostics", label: "Diagnostics", body: "Connector health and environment truth source." },
            ].map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="block rounded-[22px] border border-white/8 bg-white/[0.03] p-4 backdrop-blur-sm hover:-translate-y-[1px] hover:border-white/14 hover:bg-white/[0.05]"
              >
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <h3 className="text-base font-semibold text-white">{item.label}</h3>
                    <p className="mt-1 text-sm text-slate-300">{item.body}</p>
                  </div>
                  <span className="text-sm text-sky-200">Open →</span>
                </div>
              </Link>
            ))}
          </div>
        </SectionCard>
      </div>
    </PageShell>
  );
}
