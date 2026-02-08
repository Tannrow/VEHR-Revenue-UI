"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { apiFetch } from "@/lib/api";

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

function toErrorMessage(error: unknown, fallback: string) {
  return error instanceof Error && error.message ? error.message : fallback;
}

function todayDate() {
  return new Date().toISOString().slice(0, 10);
}

function statusBadgeClass(status: string) {
  if (status === "active" || status === "completed") {
    return "border-emerald-200 bg-emerald-50 text-emerald-700";
  }
  if (status === "required" || status === "sent") {
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

  const [activeTab, setActiveTab] = useState("overview");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [patient, setPatient] = useState<Patient | null>(null);
  const [services, setServices] = useState<Service[]>([]);
  const [enrollments, setEnrollments] = useState<Enrollment[]>([]);
  const [notes, setNotes] = useState<PatientNote[]>([]);
  const [documents, setDocuments] = useState<PatientDocument[]>([]);

  const [noteServiceFilter, setNoteServiceFilter] = useState("all");
  const [enrollmentServiceId, setEnrollmentServiceId] = useState("");
  const [enrollmentStartDate, setEnrollmentStartDate] = useState(todayDate());
  const [noteServiceId, setNoteServiceId] = useState("");
  const [noteBody, setNoteBody] = useState("");
  const [noteVisibility, setNoteVisibility] = useState<PatientNote["visibility"]>("clinical_only");

  const [sendingServiceId, setSendingServiceId] = useState<string | null>(null);
  const [sendResult, setSendResult] = useState<SendDocumentsResponse | null>(null);

  const activeServiceChips = useMemo(() => {
    const byId = new Map<string, Enrollment["service"]>();
    enrollments.filter((enrollment) => enrollment.status === "active").forEach((enrollment) => {
      byId.set(enrollment.service.id, enrollment.service);
    });
    return Array.from(byId.values());
  }, [enrollments]);

  const documentGroups = useMemo(() => {
    const grouped = new Map<string, { service: ServiceSummary; documents: PatientDocument[] }>();
    for (const document of documents) {
      if (!grouped.has(document.service.id)) {
        grouped.set(document.service.id, {
          service: document.service,
          documents: [],
        });
      }
      grouped.get(document.service.id)?.documents.push(document);
    }
    return Array.from(grouped.values());
  }, [documents]);

  const documentsByEnrollment = useMemo(() => {
    const stats = new Map<string, { total: number; completed: number }>();
    for (const document of documents) {
      if (!stats.has(document.enrollment_id)) {
        stats.set(document.enrollment_id, { total: 0, completed: 0 });
      }
      const row = stats.get(document.enrollment_id)!;
      row.total += 1;
      if (document.status === "completed") {
        row.completed += 1;
      }
    }
    return stats;
  }, [documents]);

  const refreshWorkspace = useCallback(async () => {
    if (!patientId) return;
    try {
      setLoading(true);
      setError(null);
      const [patientRes, servicesRes, enrollmentsRes, documentsRes] = await Promise.all([
        apiFetch<Patient>(`/api/v1/patients/${patientId}`, { cache: "no-store" }),
        apiFetch<Service[]>("/api/v1/services?include_inactive=true", { cache: "no-store" }),
        apiFetch<Enrollment[]>(`/api/v1/patients/${patientId}/enrollments`, { cache: "no-store" }),
        apiFetch<PatientDocument[]>(`/api/v1/patients/${patientId}/documents`, { cache: "no-store" }),
      ]);
      setPatient(patientRes);
      setServices(servicesRes);
      setEnrollments(enrollmentsRes);
      setDocuments(documentsRes);
      if (!enrollmentServiceId && servicesRes[0]) {
        setEnrollmentServiceId(servicesRes[0].id);
      }
      if (!noteServiceId && (enrollmentsRes[0]?.service.id || servicesRes[0]?.id)) {
        setNoteServiceId(enrollmentsRes[0]?.service.id || servicesRes[0].id);
      }
    } catch (loadError) {
      setError(toErrorMessage(loadError, "Failed to load patient workspace"));
    } finally {
      setLoading(false);
    }
  }, [patientId, enrollmentServiceId, noteServiceId]);

  const refreshNotes = useCallback(async () => {
    if (!patientId) return;
    try {
      const query = noteServiceFilter === "all" ? "" : `?service_id=${noteServiceFilter}`;
      const data = await apiFetch<PatientNote[]>(`/api/v1/patients/${patientId}/notes${query}`, {
        cache: "no-store",
      });
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
        body: JSON.stringify({
          service_id: enrollmentServiceId,
          status: "active",
          start_date: enrollmentStartDate,
        }),
      });
      await refreshWorkspace();
      setActiveTab("services");
    } catch (createError) {
      setError(toErrorMessage(createError, "Failed to create enrollment"));
    }
  }

  async function createNote(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!patientId || !noteServiceId || !noteBody.trim()) return;

    try {
      await apiFetch(`/api/v1/patients/${patientId}/notes`, {
        method: "POST",
        body: JSON.stringify({
          primary_service_id: noteServiceId,
          body: noteBody.trim(),
          visibility: noteVisibility,
        }),
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
      const refreshed = await apiFetch<PatientDocument[]>(`/api/v1/patients/${patientId}/documents`, {
        cache: "no-store",
      });
      setDocuments(refreshed);
    } catch (sendError) {
      setError(toErrorMessage(sendError, "Failed to send documents to patient portal"));
    } finally {
      setSendingServiceId(null);
    }
  }

  if (loading) {
    return <p className="text-sm text-slate-600">Loading patient workspace...</p>;
  }
  if (!patientId || !patient) {
    return <p className="text-sm text-rose-700">Patient not found.</p>;
  }

  return (
    <div className="space-y-6">
      {error ? (
        <div className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
          {error}
        </div>
      ) : null}

      {sendResult ? (
        <div className="rounded-lg border border-cyan-200 bg-cyan-50 p-3 text-sm text-cyan-900">
          <div className="font-semibold">Patient Portal Invite Created</div>
          <div className="mt-1">Code: <span className="font-mono">{sendResult.access_code}</span></div>
          <div className="mt-1 break-all">Magic link: {sendResult.magic_link}</div>
          <div className="mt-1 text-xs text-cyan-700">
            Expires: {new Date(sendResult.expires_at).toLocaleString()}
          </div>
        </div>
      ) : null}

      <Card className="border-slate-200/70 shadow-sm">
        <CardHeader className="border-b border-slate-200/70 bg-slate-50/70">
          <CardTitle className="text-lg">
            {patient.last_name}, {patient.first_name}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 pt-5 text-sm text-slate-700">
          <div>DOB: {patient.dob || "None"}</div>
          <div>Email: {patient.email || "None"}</div>
          <div>Phone: {patient.phone || "None"}</div>
          <div className="flex flex-wrap gap-2">
            {activeServiceChips.length === 0 ? (
              <Badge className="border-slate-200 bg-slate-100 text-slate-700">No active services</Badge>
            ) : (
              activeServiceChips.map((service) => (
                <Badge key={service.id} className="border-cyan-200 bg-cyan-50 font-mono text-cyan-700">
                  {service.code}
                </Badge>
              ))
            )}
          </div>
          <div className="rounded-md border border-dashed border-slate-200 bg-slate-50 p-3 text-xs text-slate-600">
            Alerts placeholder.
          </div>
        </CardContent>
      </Card>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="h-auto flex-wrap gap-2 rounded-xl border border-slate-200 bg-white p-2">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="services">Services</TabsTrigger>
          <TabsTrigger value="notes">Notes</TabsTrigger>
          <TabsTrigger value="documents">Documents</TabsTrigger>
          <TabsTrigger value="compliance">Compliance</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="pt-4 text-sm text-slate-600">
          One chart, multiple services. Enrollment, notes, and paperwork remain service-scoped.
        </TabsContent>

        <TabsContent value="services" className="pt-4">
          <Card className="border-slate-200/70 shadow-sm">
            <CardHeader>
              <CardTitle className="text-base">Service Enrollments</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4 pt-0">
              <form className="grid gap-2 sm:grid-cols-[1fr_auto_auto]" onSubmit={createEnrollment}>
                <select
                  className="h-9 rounded-md border border-slate-200 px-3 text-sm"
                  value={enrollmentServiceId}
                  onChange={(event) => setEnrollmentServiceId(event.target.value)}
                >
                  {services.map((service) => (
                    <option key={service.id} value={service.id}>
                      {service.code} - {service.name}
                    </option>
                  ))}
                </select>
                <Input
                  type="date"
                  value={enrollmentStartDate}
                  onChange={(event) => setEnrollmentStartDate(event.target.value)}
                />
                <Button type="submit">Enroll</Button>
              </form>

              <div className="space-y-2">
                {enrollments.map((enrollment) => {
                  const stats = documentsByEnrollment.get(enrollment.id) ?? { total: 0, completed: 0 };
                  return (
                    <div key={enrollment.id} className="rounded-md border border-slate-200 p-3 text-sm">
                      <div className="font-semibold text-slate-900">
                        {enrollment.service.name} ({enrollment.service.code})
                      </div>
                      <div className="text-slate-600">
                        Status: {enrollment.status} | {enrollment.start_date} to {enrollment.end_date || "open"}
                      </div>
                      <div className="text-slate-500">
                        Reporting: {enrollment.reporting_enabled ? "enabled" : "disabled"}
                      </div>
                      <div className="mt-1 text-xs text-slate-600">
                        Documents completed: {stats.completed}/{stats.total}
                      </div>
                    </div>
                  );
                })}
                {enrollments.length === 0 ? (
                  <div className="text-sm text-slate-600">No enrollments yet.</div>
                ) : null}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="notes" className="pt-4">
          <Card className="border-slate-200/70 shadow-sm">
            <CardHeader>
              <CardTitle className="text-base">Service-Scoped Notes</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4 pt-0">
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  size="sm"
                  variant={noteServiceFilter === "all" ? "default" : "outline"}
                  onClick={() => setNoteServiceFilter("all")}
                >
                  All
                </Button>
                {Array.from(new Map(enrollments.map((entry) => [entry.service.id, entry.service])).values()).map(
                  (service) => (
                    <Button
                      key={service.id}
                      type="button"
                      size="sm"
                      variant={noteServiceFilter === service.id ? "default" : "outline"}
                      onClick={() => setNoteServiceFilter(service.id)}
                    >
                      {service.code}
                    </Button>
                  ),
                )}
              </div>

              <form className="grid gap-2" onSubmit={createNote}>
                <div className="grid gap-2 sm:grid-cols-2">
                  <select
                    className="h-9 rounded-md border border-slate-200 px-3 text-sm"
                    value={noteServiceId}
                    onChange={(event) => setNoteServiceId(event.target.value)}
                  >
                    {Array.from(new Map(enrollments.map((entry) => [entry.service.id, entry.service])).values()).map(
                      (service) => (
                        <option key={service.id} value={service.id}>
                          {service.code} - {service.name}
                        </option>
                      ),
                    )}
                  </select>
                  <select
                    className="h-9 rounded-md border border-slate-200 px-3 text-sm"
                    value={noteVisibility}
                    onChange={(event) => setNoteVisibility(event.target.value as PatientNote["visibility"])}
                  >
                    <option value="clinical_only">clinical_only</option>
                    <option value="legal_and_clinical">legal_and_clinical</option>
                  </select>
                </div>
                <textarea
                  className="min-h-[96px] rounded-md border border-slate-200 px-3 py-2 text-sm"
                  value={noteBody}
                  onChange={(event) => setNoteBody(event.target.value)}
                />
                <Button type="submit">Add Note</Button>
              </form>

              <div className="space-y-2">
                {notes.map((note) => (
                  <div key={note.id} className="rounded-md border border-slate-200 p-3 text-sm">
                    <div className="flex flex-wrap gap-2">
                      <Badge className="border-cyan-200 bg-cyan-50 font-mono text-cyan-700">
                        {note.primary_service.code}
                      </Badge>
                      <Badge className="border-violet-200 bg-violet-50 text-violet-700">
                        {note.visibility}
                      </Badge>
                    </div>
                    <div className="mt-2 whitespace-pre-wrap text-slate-700">{note.body}</div>
                  </div>
                ))}
                {notes.length === 0 ? (
                  <div className="text-sm text-slate-600">No notes in this filter.</div>
                ) : null}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="documents" className="pt-4">
          <Card className="border-slate-200/70 shadow-sm">
            <CardHeader>
              <CardTitle className="text-base">Service Paperwork</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4 pt-0">
              {documentGroups.length === 0 ? (
                <div className="text-sm text-slate-600">No assigned paperwork yet.</div>
              ) : (
                documentGroups.map((group) => (
                  <div key={group.service.id} className="rounded-lg border border-slate-200 p-4">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="text-sm font-semibold text-slate-900">
                        {group.service.name} ({group.service.code})
                      </div>
                      <Button
                        type="button"
                        size="sm"
                        onClick={() => sendDocumentsToPortal(group.service.id)}
                        disabled={sendingServiceId === group.service.id}
                      >
                        {sendingServiceId === group.service.id ? "Sending..." : "Send to Patient Portal"}
                      </Button>
                    </div>
                    <div className="mt-3 space-y-2">
                      {group.documents.map((document) => (
                        <div
                          key={document.id}
                          className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-slate-200 px-3 py-2"
                        >
                          <div className="text-sm text-slate-800">
                            {document.template.name} v{document.template.version}
                          </div>
                          <Badge className={statusBadgeClass(document.status)}>{document.status}</Badge>
                        </div>
                      ))}
                    </div>
                  </div>
                ))
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="compliance" className="pt-4 text-sm text-slate-600">
          Compliance placeholder.
        </TabsContent>
      </Tabs>
    </div>
  );
}
