export type QueueStatus = "new" | "ready" | "blocked" | "appeal" | "resolved";
export type QueuePriority = "critical" | "high" | "medium" | "low";

export type QueueItem = {
  id: string;
  claimId: string;
  denialId: string;
  patient: string;
  payer: string;
  denialCode: string;
  denialReason: string;
  owner: string;
  queue: string;
  status: QueueStatus;
  priority: QueuePriority;
  agingDays: number;
  slaHours: number;
  amountCents: number;
  confidence: number;
  encounterId: string;
  authorizationId: string;
  patientId: string;
  documents: string[];
  nextAction: string;
  aiSummary: string;
  evidence: Array<{ label: string; detail: string }>;
  timeline: Array<{ at: string; event: string; actor: string }>;
};

export type InsightMetric = {
  label: string;
  value: string;
  trend: string;
  change: string;
  drillLabel: string;
};

export type PipelineStage = {
  label: string;
  count: number;
  tone: "neutral" | "warning" | "good";
  action: string;
};

export type PolicyRule = {
  id: string;
  name: string;
  condition: string;
  outcome: string;
  coverage: string;
};

export const revenueQueue: QueueItem[] = [
  {
    id: "WQ-2184",
    claimId: "CLM-884193",
    denialId: "DEN-01372",
    patient: "Olivia Bennett",
    payer: "Blue Cross Medicare",
    denialCode: "CO-197",
    denialReason: "Prior authorization missing on high-cost infusion visit.",
    owner: "Anika",
    queue: "Authorization salvage",
    status: "blocked",
    priority: "critical",
    agingDays: 14,
    slaHours: 6,
    amountCents: 124800,
    confidence: 92,
    encounterId: "ENC-44291",
    authorizationId: "AUTH-7183",
    patientId: "PAT-21891",
    documents: ["Physician infusion note", "Plan prior auth grid", "Referral intake"],
    nextAction: "Draft retro-auth packet and send to payer portal before SLA expires.",
    aiSummary: "This denial is recoverable because the visit documentation references a valid referral, but the prior auth number was never attached to the claim submission payload.",
    evidence: [
      { label: "Clinical note", detail: "Infusion note on 2026-03-08 includes medical necessity and ordering physician signature." },
      { label: "Payer policy", detail: "Plan allows retro-authorization within 15 calendar days for specialty infusion when documentation is complete." },
      { label: "Submission audit", detail: "837 payload did not include authorization segment." },
    ],
    timeline: [
      { at: "8:04 AM", event: "ERA structured and denial normalized", actor: "System" },
      { at: "8:06 AM", event: "AI grouped with retro-auth salvage workflow", actor: "VEHR Copilot" },
      { at: "8:12 AM", event: "Awaiting specialist action", actor: "Work queue" },
    ],
  },
  {
    id: "WQ-2181",
    claimId: "CLM-884102",
    denialId: "DEN-01359",
    patient: "Mason Rodriguez",
    payer: "Aetna Commercial",
    denialCode: "CO-45",
    denialReason: "Underpaid orthopedic surgery claim compared with contracted rate.",
    owner: "Jordan",
    queue: "Underpayment recovery",
    status: "ready",
    priority: "high",
    agingDays: 9,
    slaHours: 18,
    amountCents: 98200,
    confidence: 88,
    encounterId: "ENC-44117",
    authorizationId: "AUTH-7050",
    patientId: "PAT-21733",
    documents: ["Contract terms", "Allowed amount worksheet", "ERA line-level adjustments"],
    nextAction: "Generate reconsideration letter citing contracted ASC rate and attach line-level variance worksheet.",
    aiSummary: "Payment is $982 below the contracted ASC rate after removing patient-responsibility and sequestration adjustments.",
    evidence: [
      { label: "Contract reference", detail: "Appendix C lists CPT 29881 at $5,410 for ASC place of service." },
      { label: "ERA variance", detail: "Allowed amount paid at $4,428 after contractual adjustment sequence." },
      { label: "Prior submissions", detail: "No prior reconsideration has been sent for this claim." },
    ],
    timeline: [
      { at: "7:30 AM", event: "Variance threshold alert opened", actor: "Insight engine" },
      { at: "7:34 AM", event: "Assigned to Jordan by payer routing policy", actor: "Policy engine" },
      { at: "7:42 AM", event: "Awaiting appeal draft approval", actor: "Queue" },
    ],
  },
  {
    id: "WQ-2173",
    claimId: "CLM-883994",
    denialId: "DEN-01321",
    patient: "Sophia Patel",
    payer: "UnitedHealthcare",
    denialCode: "CO-16",
    denialReason: "Missing operative report attachment on submitted claim.",
    owner: "Nina",
    queue: "Documentation chase",
    status: "appeal",
    priority: "medium",
    agingDays: 6,
    slaHours: 24,
    amountCents: 46800,
    confidence: 81,
    encounterId: "ENC-43991",
    authorizationId: "AUTH-6948",
    patientId: "PAT-21602",
    documents: ["Op note pending signature", "Claim attachment log", "Fax confirmation"],
    nextAction: "Send signed operative report with corrected attachment cover sheet.",
    aiSummary: "The payer denial matches an attachment mismatch, not a medical necessity issue. Once the signed op note is uploaded, the reconsideration should clear quickly.",
    evidence: [
      { label: "Attachment log", detail: "Original fax contained only claim face sheet and auth approval." },
      { label: "Provider note", detail: "Operative report signed at 7:21 AM today and available in chart." },
    ],
    timeline: [
      { at: "Yesterday", event: "Missing attachment queue auto-created", actor: "VEHR Copilot" },
      { at: "Today 7:22 AM", event: "Document became available in chart", actor: "EHR sync" },
      { at: "Today 8:10 AM", event: "Ready for resend", actor: "Nina" },
    ],
  },
  {
    id: "WQ-2168",
    claimId: "CLM-883911",
    denialId: "DEN-01308",
    patient: "Liam Chen",
    payer: "Humana MA",
    denialCode: "PR-204",
    denialReason: "Patient eligibility changed retroactively; plan selection mismatch.",
    owner: "Tariq",
    queue: "Eligibility correction",
    status: "new",
    priority: "high",
    agingDays: 3,
    slaHours: 30,
    amountCents: 35600,
    confidence: 73,
    encounterId: "ENC-43875",
    authorizationId: "AUTH-6874",
    patientId: "PAT-21542",
    documents: ["Eligibility response history", "Registration notes", "Member card image"],
    nextAction: "Confirm retroactive plan term, then rebill to replacement payer if coverage transfer is valid.",
    aiSummary: "There is conflicting eligibility data between registration and payer response history. The replacement plan likely became active two days before DOS.",
    evidence: [
      { label: "Eligibility trace", detail: "271 response on DOS shows active plan H3442, while registration stored H1036." },
      { label: "Registration note", detail: "Front desk captured new member card but payer ID was not updated in PM system." },
    ],
    timeline: [
      { at: "6:54 AM", event: "Claim imported from rebill monitor", actor: "System" },
      { at: "7:01 AM", event: "Eligibility mismatch flagged", actor: "Insight engine" },
    ],
  },
];

export const insightMetrics: InsightMetric[] = [
  { label: "Denial dollars at risk", value: "$1.84M", trend: "Spiking in ortho and infusion", change: "+11.2%", drillLabel: "Open impacted queue" },
  { label: "Appeals ready today", value: "43", trend: "Most are evidence-complete", change: "+9", drillLabel: "Review appeal-ready items" },
  { label: "AI-suggested recoveries", value: "$412K", trend: "High confidence recommendations", change: "87% confidence", drillLabel: "Inspect AI evidence" },
  { label: "SLA breaches in 24h", value: "7", trend: "Concentrated with two payers", change: "-3 vs yesterday", drillLabel: "Escalate owners" },
];

export const pipelineStages: PipelineStage[] = [
  { label: "ERA intake", count: 12, tone: "good", action: "Review processed remits" },
  { label: "Normalization", count: 4, tone: "neutral", action: "Inspect structuring output" },
  { label: "Human review", count: 18, tone: "warning", action: "Open work queue" },
  { label: "Appeal submitted", count: 29, tone: "neutral", action: "Track payer responses" },
  { label: "Resolved", count: 64, tone: "good", action: "Review outcomes" },
];

export const policyRules: PolicyRule[] = [
  {
    id: "POL-12",
    name: "Retro-auth salvage",
    condition: "If denial code = CO-197 and amount > $750 and payer allows retro-auth",
    outcome: "Route to Authorization salvage queue, assign within 15 minutes, require document evidence pack",
    coverage: "14 active claims",
  },
  {
    id: "POL-09",
    name: "Underpayment escalation",
    condition: "If variance > 10% of billed and payer in contracted plans",
    outcome: "Create underpayment work item, draft reconsideration, send to manager approval",
    coverage: "22 active claims",
  },
  {
    id: "POL-03",
    name: "Missing records chase",
    condition: "If denial code in CO-16 group and op note missing",
    outcome: "Open documentation chase playbook and snooze until signed note arrives",
    coverage: "9 active claims",
  },
];

export const savedViews = [
  "My critical work",
  "Appeals ready to submit",
  "New payer anomalies",
  "Authorization salvage",
  "Documentation chase",
];

export const commandSuggestions = [
  "Assign selected items to Jordan",
  "Draft appeal for Blue Cross denials",
  "Open claim CLM-884193",
  "Show underpayments over $500",
  "Escalate Humana SLA breaches",
];
