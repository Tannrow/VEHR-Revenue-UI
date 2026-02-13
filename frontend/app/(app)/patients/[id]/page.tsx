
"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ApiError, apiFetch } from "@/lib/api";
import { isUiV2ClientProfileEnabled } from "@/lib/feature-flags";

type Patient = {
  id: string;
  first_name: string;
  last_name: string;
  dob?: string | null;
  phone?: string | null;
  email?: string | null;
};

type Service = {
  id: string;
  name: string;
  code: string;
  category: "intake" | "sud" | "mh" | "psych" | "cm";
  is_active: boolean;
};

type ServiceSummary = Pick<Service, "id" | "name" | "code" | "category">;

type Enrollment = {
  id: string;
  status: "active" | "paused" | "discharged";
  start_date: string;
  end_date?: string | null;
  reporting_enabled: boolean;
  service: ServiceSummary;
};

type Encounter = {
  id: string;
  encounter_type: string;
  start_time: string;
  end_time?: string | null;
  clinician?: string | null;
  location?: string | null;
  modality?: string | null;
};

type Episode = {
  id: string;
  patient_id: string;
  admit_date: string;
  discharge_date?: string | null;
  primary_service_category: string;
  court_involved: boolean;
  status: "active" | "discharged";
  referral_source?: string | null;
  reason_for_admission?: string | null;
  discharge_disposition?: string | null;
};

type CareTeamMember = {
  id: string;
  patient_id: string;
  episode_id: string;
  role: string;
  user_id: string;
  assigned_at: string;
  user_email: string;
  user_full_name?: string | null;
};

type Requirement = {
  id: string;
  patient_id: string;
  episode_id: string;
  requirement_type: string;
  status: "open" | "resolved";
  auto_generated: boolean;
  resolved_at?: string | null;
};

type TreatmentStage = {
  id?: string | null;
  episode_id?: string | null;
  stage?: string | null;
  updated_at?: string | null;
};

type StageEvent = {
  id: string;
  episode_id: string;
  from_stage?: string | null;
  to_stage: string;
  reason?: string | null;
  created_at: string;
};

type PatientNote = {
  id: string;
  body: string;
  visibility: "clinical_only" | "legal_and_clinical";
  created_at: string;
  primary_service: ServiceSummary;
};

type PatientDocument = {
  id: string;
  patient_id: string;
  service_id: string;
  enrollment_id: string;
  template_id: string;
  status: "required" | "sent" | "completed" | "expired";
  completed_at?: string | null;
  expires_at?: string | null;
  sent_at?: string | null;
  created_at: string;
  updated_at: string;
  service: ServiceSummary;
  template: {
    id: string;
    name: string;
    version: number;
    status: string;
  };
};

type SendDocumentsResponse = {
  sent_document_ids: string[];
  access_code: string;
  magic_link: string;
  expires_at: string;
};

const STAGE_ORDER = [
  { key: "intake_started", label: "Intake Started" },
  { key: "paperwork_completed", label: "Paperwork Completed" },
  { key: "assessment_completed", label: "Assessment Completed" },
  { key: "enrolled", label: "Enrolled" },
  { key: "active_treatment", label: "Active Treatment" },
  { key: "step_down_transition", label: "Step-Down / Transition" },
  { key: "discharge_planning", label: "Discharge Planning" },
  { key: "discharged", label: "Discharged" },
] as const;

function toErrorMessage(error: unknown, fallback: string) {
  return error instanceof Error && error.message ? error.message : fallback;
}

function todayDate() {
  return new Date().toISOString().slice(0, 10);
}

function statusBadgeClass(status: string) {
  if (status === "active" || status === "completed" || status === "resolved") {
    return "border-emerald-200 bg-emerald-50 text-emerald-700";
  }
  if (status === "required" || status === "sent" || status === "open") {
    return "border-cyan-200 bg-cyan-50 text-cyan-700";
  }
  if (status === "paused" || status === "expired") {
    return "border-amber-200 bg-amber-50 text-amber-700";
  }
  return "border-slate-200 bg-slate-100 text-slate-700";
}

export default function PatientWorkspacePage() {
  const params = useParams();
  const patientId = Array.isArray(params?.id) ? params.id[0] : params?.id;
  const uiV2ClientProfileEnabled = isUiV2ClientProfileEnabled();

  const [activeTab, setActiveTab] = useState("overview");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [patient, setPatient] = useState<Patient | null>(null);
  const [services, setServices] = useState<Service[]>([]);
  const [enrollments, setEnrollments] = useState<Enrollment[]>([]);
  const [encounters, setEncounters] = useState<Encounter[]>([]);
  const [episodes, setEpisodes] = useState<Episode[]>([]);
  const [careTeam, setCareTeam] = useState<CareTeamMember[]>([]);
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [treatmentStage, setTreatmentStage] = useState<TreatmentStage | null>(null);
  const [stageEvents, setStageEvents] = useState<StageEvent[]>([]);

  const [notes, setNotes] = useState<PatientNote[]>([]);
  const [documents, setDocuments] = useState<PatientDocument[]>([]);
  const [noteServiceFilter, setNoteServiceFilter] = useState("all");
  const [noteServiceId, setNoteServiceId] = useState("");
  const [noteBody, setNoteBody] = useState("");
  const [noteVisibility, setNoteVisibility] = useState<PatientNote["visibility"]>("clinical_only");

  const [enrollmentServiceId, setEnrollmentServiceId] = useState("");
  const [enrollmentStartDate, setEnrollmentStartDate] = useState(todayDate());
  const [encounterType, setEncounterType] = useState("contact");
  const [encounterDateTime, setEncounterDateTime] = useState(`${todayDate()}T09:00`);

  const [sendingServiceId, setSendingServiceId] = useState<string | null>(null);
  const [sendResult, setSendResult] = useState<SendDocumentsResponse | null>(null);
  const [stageUpdating, setStageUpdating] = useState(false);

  const activeEpisode = useMemo(() => episodes.find((entry) => entry.status === "active") ?? null, [episodes]);
  const activeServiceChips = useMemo(() => {
    const byId = new Map<string, Enrollment["service"]>();
    enrollments.filter((entry) => entry.status === "active").forEach((entry) => byId.set(entry.service.id, entry.service));
    return Array.from(byId.values());
  }, [enrollments]);
  const openRequirements = useMemo(() => requirements.filter((entry) => entry.status === "open"), [requirements]);

  const readinessChecklist = useMemo(() => {
    const openByType = new Set(openRequirements.map((entry) => entry.requirement_type));
    return [
      { label: "Demographics complete", done: !openByType.has("missing_demographics") },
      { label: "Insurance verified", done: !openByType.has("missing_insurance") },
      { label: "Consent completed", done: !openByType.has("missing_consent") },
      { label: "Intake assessment completed", done: !openByType.has("missing_assessment") },
      { label: "Care team assigned", done: careTeam.length > 0 },
    ];
  }, [openRequirements, careTeam.length]);

  const documentGroups = useMemo(() => {
    const grouped = new Map<string, { service: ServiceSummary; documents: PatientDocument[] }>();
    for (const document of documents) {
      if (!grouped.has(document.service.id)) {
        grouped.set(document.service.id, { service: document.service, documents: [] });
      }
      grouped.get(document.service.id)?.documents.push(document);
    }
    return Array.from(grouped.values());
  }, [documents]);

  const currentStageIndex = useMemo(() => {
    if (!treatmentStage?.stage) return 0;
    const idx = STAGE_ORDER.findIndex((entry) => entry.key === treatmentStage.stage);
    return idx < 0 ? 0 : idx;
  }, [treatmentStage?.stage]);
  const safeFetchOptional = useCallback(async <T,>(path: string): Promise<T | null> => {
    try {
      return await apiFetch<T>(path, { cache: "no-store" });
    } catch (fetchError) {
      if (fetchError instanceof ApiError && fetchError.status === 404) {
        return null;
      }
      throw fetchError;
    }
  }, []);

  const refreshWorkspace = useCallback(async () => {
    if (!patientId) return;
    try {
      setLoading(true);
      setError(null);

      const [patientRes, servicesRes, enrollmentsRes, documentsRes, encountersRes] = await Promise.all([
        apiFetch<Patient>(`/api/v1/patients/${patientId}`, { cache: "no-store" }),
        apiFetch<Service[]>("/api/v1/services?include_inactive=true", { cache: "no-store" }),
        apiFetch<Enrollment[]>(`/api/v1/patients/${patientId}/enrollments`, { cache: "no-store" }),
        apiFetch<PatientDocument[]>(`/api/v1/patients/${patientId}/documents`, { cache: "no-store" }),
        apiFetch<Encounter[]>(`/api/v1/patients/${patientId}/encounters`, { cache: "no-store" }),
      ]);

      const [episodesRes, careTeamRes, requirementsRes, stageRes, stageEventsRes] = await Promise.all([
        safeFetchOptional<Episode[]>(`/api/v1/patients/${patientId}/episodes`),
        safeFetchOptional<CareTeamMember[]>(`/api/v1/patients/${patientId}/care-team`),
        safeFetchOptional<Requirement[]>(`/api/v1/patients/${patientId}/requirements`),
        safeFetchOptional<TreatmentStage>(`/api/v1/patients/${patientId}/treatment-stage`),
        safeFetchOptional<StageEvent[]>(`/api/v1/patients/${patientId}/treatment-stage/events`),
      ]);

      setPatient(patientRes);
      setServices(servicesRes);
      setEnrollments(enrollmentsRes);
      setDocuments(documentsRes);
      setEncounters(encountersRes);
      setEpisodes(episodesRes ?? []);
      setCareTeam(careTeamRes ?? []);
      setRequirements(requirementsRes ?? []);
      setTreatmentStage(stageRes);
      setStageEvents(stageEventsRes ?? []);

      if (!enrollmentServiceId && servicesRes[0]) {
        setEnrollmentServiceId(servicesRes[0].id);
      }
      if (!noteServiceId && (enrollmentsRes[0]?.service.id || servicesRes[0]?.id)) {
        setNoteServiceId(enrollmentsRes[0]?.service.id || servicesRes[0].id);
      }
    } catch (loadError) {
      setError(toErrorMessage(loadError, "Failed to load patient chart"));
    } finally {
      setLoading(false);
    }
  }, [enrollmentServiceId, noteServiceId, patientId, safeFetchOptional]);

  const refreshNotes = useCallback(async () => {
    if (!patientId) return;
    try {
      const query = noteServiceFilter === "all" ? "" : `?service_id=${noteServiceFilter}`;
      const data = await apiFetch<PatientNote[]>(`/api/v1/patients/${patientId}/notes${query}`, { cache: "no-store" });
      setNotes(data);
    } catch (loadError) {
      setError(toErrorMessage(loadError, "Failed to load notes"));
    }
  }, [patientId, noteServiceFilter]);

  useEffect(() => {
    refreshWorkspace();
  }, [refreshWorkspace]);

  useEffect(() => {
    refreshNotes();
  }, [refreshNotes]);

  async function createEnrollment(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!patientId || !enrollmentServiceId) return;
    try {
      await apiFetch(`/api/v1/patients/${patientId}/enrollments`, {
        method: "POST",
        body: JSON.stringify({ service_id: enrollmentServiceId, status: "active", start_date: enrollmentStartDate }),
      });
      await refreshWorkspace();
      setActiveTab("intake");
    } catch (createError) {
      setError(toErrorMessage(createError, "Failed to create enrollment"));
    }
  }

  async function createEncounter(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!patientId) return;
    try {
      await apiFetch(`/api/v1/patients/${patientId}/encounters`, {
        method: "POST",
        body: JSON.stringify({ encounter_type: encounterType, start_time: new Date(encounterDateTime).toISOString() }),
      });
      await refreshWorkspace();
      setActiveTab("encounters");
    } catch (createError) {
      setError(toErrorMessage(createError, "Failed to create encounter"));
    }
  }

  async function createNote(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!patientId || !noteServiceId || !noteBody.trim()) return;
    try {
      await apiFetch(`/api/v1/patients/${patientId}/notes`, {
        method: "POST",
        body: JSON.stringify({ primary_service_id: noteServiceId, body: noteBody.trim(), visibility: noteVisibility }),
      });
      setNoteBody("");
      await refreshNotes();
    } catch (createError) {
      setError(toErrorMessage(createError, "Failed to create note"));
    }
  }

  async function sendDocumentsToPortal(serviceId: string) {
    if (!patientId) return;
    try {
      setSendingServiceId(serviceId);
      setError(null);
      const data = await apiFetch<SendDocumentsResponse>(`/api/v1/patients/${patientId}/documents/send`, {
        method: "POST",
        body: JSON.stringify({ service_id: serviceId }),
      });
      setSendResult(data);
      await refreshWorkspace();
    } catch (sendError) {
      setError(toErrorMessage(sendError, "Failed to send documents to patient portal"));
    } finally {
      setSendingServiceId(null);
    }
  }

  async function refreshRequirements() {
    if (!patientId) return;
    try {
      const rows = await apiFetch<Requirement[]>(`/api/v1/patients/${patientId}/requirements/refresh`, { method: "POST" });
      setRequirements(rows);
    } catch (refreshError) {
      setError(toErrorMessage(refreshError, "Failed to refresh requirements"));
    }
  }

  async function updateStage(stage: string) {
    if (!patientId) return;
    try {
      setStageUpdating(true);
      const next = await apiFetch<TreatmentStage>(`/api/v1/patients/${patientId}/treatment-stage`, {
        method: "POST",
        body: JSON.stringify({ stage }),
      });
      setTreatmentStage(next);
      const history = await apiFetch<StageEvent[]>(`/api/v1/patients/${patientId}/treatment-stage/events`, { cache: "no-store" });
      setStageEvents(history);
    } catch (stageError) {
      setError(toErrorMessage(stageError, "Failed to update treatment stage"));
    } finally {
      setStageUpdating(false);
    }
  }

  if (loading) {
    return <p className="text-sm text-slate-600">Loading patient chart...</p>;
  }
  if (!patientId || !patient) {
    return <p className="text-sm text-rose-700">Patient not found.</p>;
  }

  const mrn = patient.id.slice(0, 8).toUpperCase();
  return (
    <div className="space-y-6" data-testid="client-profile-page">
      {error ? <div className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{error}</div> : null}

      {sendResult ? (
        <div className="rounded-lg border border-cyan-200 bg-cyan-50 p-3 text-sm text-cyan-900">
          <div className="font-semibold">Patient Portal Invite Created</div>
          <div className="mt-1">Code: <span className="font-mono">{sendResult.access_code}</span></div>
          <div className="mt-1 break-all">Magic link: {sendResult.magic_link}</div>
          <div className="mt-1 text-xs text-cyan-700">Expires: {new Date(sendResult.expires_at).toLocaleString()}</div>
        </div>
      ) : null}

      <Card className="sticky top-4 z-20 border-slate-200/80 shadow-sm backdrop-blur">
        <CardContent className="space-y-3 p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="text-xl font-semibold text-slate-900">{patient.last_name}, {patient.first_name}</div>
              <div className="text-sm text-slate-600">DOB: {patient.dob || "Unknown"} | MRN: {mrn}</div>
              <div className="text-sm text-slate-600">
                Episode: {activeEpisode ? `${activeEpisode.status} (admit ${activeEpisode.admit_date})` : "No active episode"}
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                size="sm"
                variant="outline"
                data-testid="client-action-new-encounter"
                onClick={() => setActiveTab("encounters")}
              >
                New Encounter
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                data-testid="client-action-add-note"
                onClick={() => setActiveTab("notes")}
              >
                Add Note
              </Button>
              <Button type="button" size="sm" variant="outline" asChild>
                <Link href="/tasks" data-testid="client-action-create-task">Create Task</Link>
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                data-testid="client-action-upload-doc"
                onClick={() => setActiveTab("documents")}
              >
                Upload Doc
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => setActiveTab("assessments")}
              >
                Start Assessment
              </Button>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {activeServiceChips.map((service) => (
              <Badge key={service.id} className="border-cyan-200 bg-cyan-50 font-mono text-cyan-700">{service.code}</Badge>
            ))}
            {activeServiceChips.length === 0 ? <Badge className="border-slate-200 bg-slate-100 text-slate-700">No active services</Badge> : null}
          </div>
          <div className="flex flex-wrap gap-2 text-xs text-slate-600">
            {careTeam.map((member) => (
              <Badge key={member.id} className="border-slate-200 bg-slate-100 text-slate-700">
                {member.role.replaceAll("_", " ")}: {member.user_full_name || member.user_email}
              </Badge>
            ))}
            {careTeam.length === 0 ? <span>No care team assigned.</span> : null}
          </div>
        </CardContent>
      </Card>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList
          className="h-auto flex-wrap gap-2 rounded-xl border border-slate-200 bg-white p-2"
          data-testid="client-profile-tabs"
          data-ui-v2-enabled={uiV2ClientProfileEnabled ? "1" : "0"}
        >
          <TabsTrigger value="overview" data-testid="client-tab-overview">Overview</TabsTrigger>
          <TabsTrigger value="demographics" data-testid="client-tab-demographics">Demographics</TabsTrigger>
          <TabsTrigger value="insurance" data-testid="client-tab-insurance">Insurance</TabsTrigger>
          <TabsTrigger value="intake" data-testid="client-tab-intake">Intake & Paperwork</TabsTrigger>
          <TabsTrigger value="encounters" data-testid="client-tab-encounters">Encounters</TabsTrigger>
          <TabsTrigger value="notes" data-testid="client-tab-notes">Notes</TabsTrigger>
          <TabsTrigger value="assessments" data-testid="client-tab-assessments">Assessments</TabsTrigger>
          <TabsTrigger value="documents" data-testid="client-tab-documents">Documents</TabsTrigger>
          <TabsTrigger value="progress" data-testid="client-tab-progress">Treatment Progress</TabsTrigger>
          <TabsTrigger value="history" data-testid="client-tab-history">History</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-4 pt-4">
          <Card className="border-slate-200/70 shadow-sm">
            <CardHeader className="border-b border-slate-200/70 bg-slate-50/70"><CardTitle className="text-base">Treatment Progress</CardTitle></CardHeader>
            <CardContent className="space-y-4 pt-5">
              <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
                {STAGE_ORDER.map((stage, idx) => (
                  <div key={stage.key} className={`rounded-md border p-2 text-xs ${idx <= currentStageIndex ? "border-cyan-300 bg-cyan-50 text-cyan-800" : "border-slate-200 bg-white text-slate-500"}`}>{stage.label}</div>
                ))}
              </div>
            </CardContent>
          </Card>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card className="border-slate-200/70 shadow-sm">
              <CardHeader className="border-b border-slate-200/70 bg-slate-50/70"><CardTitle className="text-base">Readiness Checklist</CardTitle></CardHeader>
              <CardContent className="space-y-2 pt-5">
                {readinessChecklist.map((item) => (
                  <div key={item.label} className="flex items-center justify-between rounded-md border border-slate-200 px-3 py-2 text-sm">
                    <span>{item.label}</span>
                    <Badge className={item.done ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-amber-200 bg-amber-50 text-amber-700"}>{item.done ? "Complete" : "Pending"}</Badge>
                  </div>
                ))}
                <Button type="button" variant="outline" size="sm" onClick={refreshRequirements}>Refresh Requirements</Button>
              </CardContent>
            </Card>

            <Card className="border-slate-200/70 shadow-sm">
              <CardHeader className="border-b border-slate-200/70 bg-slate-50/70"><CardTitle className="text-base">Alerts</CardTitle></CardHeader>
              <CardContent className="space-y-2 pt-5">
                {openRequirements.length === 0 ? <div className="text-sm text-slate-600">No open requirements.</div> : openRequirements.map((item) => (
                  <div key={item.id} className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">{item.requirement_type.replaceAll("_", " ")}</div>
                ))}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="demographics" className="pt-4"><Card className="border-slate-200/70 shadow-sm"><CardHeader><CardTitle className="text-base">Demographics</CardTitle></CardHeader><CardContent className="grid gap-3 pt-0 sm:grid-cols-2"><Input value={patient.first_name} readOnly /><Input value={patient.last_name} readOnly /><Input value={patient.dob || ""} readOnly placeholder="DOB" /><Input value={patient.phone || ""} readOnly placeholder="Phone" /><Input value={patient.email || ""} readOnly placeholder="Email" /><Input value={mrn} readOnly placeholder="MRN" /><div className="sm:col-span-2 text-xs text-slate-500">Structured demographic editing API is planned in next increment.</div></CardContent></Card></TabsContent>

        <TabsContent value="insurance" className="pt-4"><Card className="border-slate-200/70 shadow-sm"><CardHeader><CardTitle className="text-base">Insurance</CardTitle></CardHeader><CardContent className="space-y-2 pt-0 text-sm text-slate-600"><div>Insurance fields are scaffolded; persistence model is pending.</div><Badge className={statusBadgeClass(openRequirements.some((r) => r.requirement_type === "missing_insurance") ? "open" : "resolved")}>{openRequirements.some((r) => r.requirement_type === "missing_insurance") ? "Missing insurance requirement open" : "No missing insurance requirement"}</Badge></CardContent></Card></TabsContent>

        <TabsContent value="intake" className="pt-4 space-y-4"><Card className="border-slate-200/70 shadow-sm"><CardHeader><CardTitle className="text-base">Pre-Assessment Packet & Enrollment</CardTitle></CardHeader><CardContent className="space-y-4 pt-0"><form className="grid gap-2 sm:grid-cols-[1fr_auto_auto]" onSubmit={createEnrollment}><select className="h-9 rounded-md border border-slate-200 px-3 text-sm" value={enrollmentServiceId} onChange={(event) => setEnrollmentServiceId(event.target.value)}>{services.map((service) => (<option key={service.id} value={service.id}>{service.code} - {service.name}</option>))}</select><Input type="date" value={enrollmentStartDate} onChange={(event) => setEnrollmentStartDate(event.target.value)} /><Button type="submit">Enroll</Button></form><div className="space-y-2">{enrollments.map((entry) => (<div key={entry.id} className="rounded-md border border-slate-200 p-3 text-sm"><div className="font-semibold text-slate-900">{entry.service.name} ({entry.service.code})</div><div className="text-slate-600">{entry.status} | {entry.start_date} - {entry.end_date || "open"}</div></div>))}{enrollments.length === 0 ? <div className="text-sm text-slate-600">No enrollments yet.</div> : null}</div></CardContent></Card></TabsContent>

        <TabsContent value="encounters" className="pt-4 space-y-4"><Card className="border-slate-200/70 shadow-sm"><CardHeader><CardTitle className="text-base">New Encounter</CardTitle></CardHeader><CardContent className="pt-0"><form className="grid gap-2 sm:grid-cols-[1fr_1fr_auto]" onSubmit={createEncounter}><Input value={encounterType} onChange={(event) => setEncounterType(event.target.value)} placeholder="Encounter type" /><Input type="datetime-local" value={encounterDateTime} onChange={(event) => setEncounterDateTime(event.target.value)} /><Button type="submit">Create</Button></form></CardContent></Card><Card className="border-slate-200/70 shadow-sm"><CardHeader><CardTitle className="text-base">Encounter Timeline</CardTitle></CardHeader><CardContent className="space-y-2 pt-0">{encounters.map((entry) => (<div key={entry.id} className="rounded-md border border-slate-200 p-3 text-sm"><div className="font-semibold text-slate-900">{entry.encounter_type}</div><div className="text-slate-600">{new Date(entry.start_time).toLocaleString()}</div></div>))}{encounters.length === 0 ? <div className="text-sm text-slate-600">No encounters yet.</div> : null}</CardContent></Card></TabsContent>

        <TabsContent value="notes" className="pt-4"><Card className="border-slate-200/70 shadow-sm"><CardHeader><CardTitle className="text-base">Notes</CardTitle></CardHeader><CardContent className="space-y-4 pt-0"><div className="flex flex-wrap gap-2"><Button type="button" size="sm" variant={noteServiceFilter === "all" ? "default" : "outline"} onClick={() => setNoteServiceFilter("all")}>All</Button>{Array.from(new Map(enrollments.map((entry) => [entry.service.id, entry.service])).values()).map((service) => (<Button key={service.id} type="button" size="sm" variant={noteServiceFilter === service.id ? "default" : "outline"} onClick={() => setNoteServiceFilter(service.id)}>{service.code}</Button>))}</div><form className="grid gap-2" onSubmit={createNote}><div className="grid gap-2 sm:grid-cols-2"><select className="h-9 rounded-md border border-slate-200 px-3 text-sm" value={noteServiceId} onChange={(event) => setNoteServiceId(event.target.value)}>{Array.from(new Map(enrollments.map((entry) => [entry.service.id, entry.service])).values()).map((service) => (<option key={service.id} value={service.id}>{service.code} - {service.name}</option>))}</select><select className="h-9 rounded-md border border-slate-200 px-3 text-sm" value={noteVisibility} onChange={(event) => setNoteVisibility(event.target.value as PatientNote["visibility"])}><option value="clinical_only">clinical_only</option><option value="legal_and_clinical">legal_and_clinical</option></select></div><textarea data-testid="client-note-input" className="min-h-[96px] rounded-md border border-slate-200 px-3 py-2 text-sm" value={noteBody} onChange={(event) => setNoteBody(event.target.value)} /><Button type="submit" data-testid="client-note-submit">Add Note</Button></form><div className="space-y-2">{notes.map((note) => (<div key={note.id} className="rounded-md border border-slate-200 p-3 text-sm"><div className="flex flex-wrap gap-2"><Badge className="border-cyan-200 bg-cyan-50 font-mono text-cyan-700">{note.primary_service.code}</Badge><Badge className="border-violet-200 bg-violet-50 text-violet-700">{note.visibility}</Badge></div><div className="mt-2 whitespace-pre-wrap text-slate-700">{note.body}</div></div>))}{notes.length === 0 ? <div className="text-sm text-slate-600">No notes in this filter.</div> : null}</div></CardContent></Card></TabsContent>

        <TabsContent value="assessments" className="pt-4"><Card className="border-slate-200/70 shadow-sm"><CardHeader><CardTitle className="text-base">Assessments</CardTitle></CardHeader><CardContent className="space-y-2 pt-0 text-sm text-slate-600"><div>ASAM / PHQ-9 / GAD-7 containers are planned in the next backend increment.</div><Button type="button" variant="outline" onClick={() => setActiveTab("notes")}>Capture Assessment Summary Note</Button></CardContent></Card></TabsContent>

        <TabsContent value="documents" className="pt-4"><Card className="border-slate-200/70 shadow-sm"><CardHeader><CardTitle className="text-base">Documents</CardTitle></CardHeader><CardContent className="space-y-4 pt-0" data-testid="client-documents-list">{documentGroups.length === 0 ? <div className="text-sm text-slate-600">No assigned paperwork yet.</div> : documentGroups.map((group) => (<div key={group.service.id} className="rounded-lg border border-slate-200 p-4"><div className="flex flex-wrap items-center justify-between gap-2"><div className="text-sm font-semibold text-slate-900">{group.service.name} ({group.service.code})</div><Button type="button" size="sm" data-testid={`client-doc-send-${group.service.id}`} onClick={() => sendDocumentsToPortal(group.service.id)} disabled={sendingServiceId === group.service.id}>{sendingServiceId === group.service.id ? "Sending..." : "Send to Patient Portal"}</Button></div><div className="mt-3 space-y-2">{group.documents.map((document) => (<div key={document.id} className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-slate-200 px-3 py-2"><div className="text-sm text-slate-800">{document.template.name} v{document.template.version}</div><Badge className={statusBadgeClass(document.status)}>{document.status}</Badge></div>))}</div></div>))}</CardContent></Card></TabsContent>

        <TabsContent value="progress" className="pt-4"><Card className="border-slate-200/70 shadow-sm"><CardHeader><CardTitle className="text-base">Treatment Stage</CardTitle></CardHeader><CardContent className="space-y-3 pt-0"><div className="grid gap-2 sm:grid-cols-2">{STAGE_ORDER.map((stage) => (<Button key={stage.key} type="button" variant={treatmentStage?.stage === stage.key ? "default" : "outline"} disabled={stageUpdating} onClick={() => updateStage(stage.key)}>{stage.label}</Button>))}</div><div className="space-y-2">{stageEvents.map((event) => (<div key={event.id} className="rounded-md border border-slate-200 px-3 py-2 text-sm"><div className="font-semibold text-slate-900">{event.to_stage.replaceAll("_", " ")}</div><div className="text-slate-600">{new Date(event.created_at).toLocaleString()}</div>{event.reason ? <div className="text-xs text-slate-500">{event.reason}</div> : null}</div>))}{stageEvents.length === 0 ? <div className="text-sm text-slate-600">No stage history yet.</div> : null}</div></CardContent></Card></TabsContent>

        <TabsContent value="history" className="pt-4"><Card className="border-slate-200/70 shadow-sm"><CardHeader><CardTitle className="text-base">History</CardTitle></CardHeader><CardContent className="space-y-2 pt-0">{episodes.map((episode) => (<div key={episode.id} className="rounded-md border border-slate-200 px-3 py-2 text-sm"><div className="font-semibold text-slate-900">Episode {episode.status}</div><div className="text-slate-600">Admit {episode.admit_date}{episode.discharge_date ? ` | Discharge ${episode.discharge_date}` : ""}</div></div>))}{notes.slice(0, 5).map((note) => (<div key={note.id} className="rounded-md border border-slate-200 px-3 py-2 text-sm text-slate-700">Note ({note.primary_service.code}) - {new Date(note.created_at).toLocaleString()}</div>))}{episodes.length === 0 && notes.length === 0 ? <div className="text-sm text-slate-600">No activity yet.</div> : null}</CardContent></Card></TabsContent>
      </Tabs>
    </div>
  );
}
