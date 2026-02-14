import { FileText, ShieldCheck, Stethoscope } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { AppLayoutPageConfig } from "@/lib/app-layout-config";

const DOCUMENT_SECTIONS = [
  {
    title: "Clinical Policies",
    description: "Patient care standards, intake forms, and encounter documentation guidance.",
    icon: Stethoscope,
  },
  {
    title: "Compliance Library",
    description: "Regulatory requirements, audit-ready policy references, and required attestations.",
    icon: ShieldCheck,
  },
  {
    title: "Operational Documents",
    description: "Team procedures, internal playbooks, and role-based process documentation.",
    icon: FileText,
  },
];

export default function DocumentsPage() {
  return (
    <div className="flex flex-col gap-6">
      <AppLayoutPageConfig
        moduleLabel="Care Delivery"
        pageTitle="Documents"
        subtitle="Internal clinic resources and policy libraries."
      />

      <div className="space-y-2">
        <h1 className="text-3xl font-semibold tracking-tight text-slate-900">Documents</h1>
        <p className="text-sm text-slate-600">Browse internal document collections by category.</p>
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {DOCUMENT_SECTIONS.map((section) => {
          const Icon = section.icon;
          return (
            <Card key={section.title} className="border-slate-200/70 shadow-sm">
              <CardHeader className="border-b border-slate-200/70 bg-slate-50/70">
                <CardTitle className="flex items-center gap-2 text-base text-slate-900">
                  <Icon className="h-4 w-4 text-slate-600" />
                  {section.title}
                </CardTitle>
              </CardHeader>
              <CardContent className="pt-5 text-sm text-slate-600">{section.description}</CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
