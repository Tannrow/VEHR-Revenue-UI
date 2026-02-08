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

type Enrollment = {
  id: string;
  status: "active" | "paused" | "discharged";
  start_date: string;
  end_date?: string | null;
  reporting_enabled: boolean;
  service: Pick<Service, "id" | "name" | "code" | "category">;
};

type PatientNote = {
  id: string;
  body: string;
  visibility: "clinical_only" | "legal_and_clinical";
  created_at: string;
  primary_service: Pick<Service, "id" | "name" | "code" | "category">;
};

function toErrorMessage(error: unknown, fallback: string) {
  return error instanceof Error && error.message ? error.message : fallback;
}

function todayDate() {
  return new Date().toISOString().slice(0, 10);
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

  const [noteServiceFilter, setNoteServiceFilter] = useState("all");
  const [enrollmentServiceId, setEnrollmentServiceId] = useState("");
  const [enrollmentStartDate, setEnrollmentStartDate] = useState(todayDate());
  const [noteServiceId, setNoteServiceId] = useState("");
  const [noteBody, setNoteBody] = useState("");
  const [noteVisibility, setNoteVisibility] = useState<PatientNote["visibility"]>("clinical_only");

  const activeServiceChips = useMemo(() => {
    const byId = new Map<string, Enrollment["service"]>();
    enrollments.filter((e) => e.status === "active").forEach((enrollment) => {
      byId.set(enrollment.service.id, enrollment.service);
    });
    return Array.from(byId.values());
  }, [enrollments]);

  const refreshWorkspace = useCallback(async () => {
    if (!patientId) return;
    try {
      setLoading(true);
      setError(null);
      const [patientRes, servicesRes, enrollmentsRes] = await Promise.all([
        apiFetch<Patient>(`/api/v1/patients/${patientId}`, { cache: "no-store" }),
        apiFetch<Service[]>("/api/v1/services?include_inactive=true", { cache: "no-store" }),
        apiFetch<Enrollment[]>(`/api/v1/patients/${patientId}/enrollments`, { cache: "no-store" }),
      ]);
      setPatient(patientRes);
      setServices(servicesRes);
      setEnrollments(enrollmentsRes);
      if (!enrollmentServiceId && servicesRes[0]) setEnrollmentServiceId(servicesRes[0].id);
      if (!noteServiceId && (enrollmentsRes[0]?.service.id || servicesRes[0]?.id)) {
        setNoteServiceId(enrollmentsRes[0]?.service.id || servicesRes[0].id);
      }
    } catch (e) {
      setError(toErrorMessage(e, "Failed to load patient workspace"));
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
    } catch (e) {
      setError(toErrorMessage(e, "Failed to load notes"));
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
    } catch (e) {
      setError(toErrorMessage(e, "Failed to create enrollment"));
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
    } catch (e) {
      setError(toErrorMessage(e, "Failed to create note"));
    }
  }

  if (loading) return <p className="text-sm text-slate-600">Loading patient workspace...</p>;
  if (!patientId || !patient) return <p className="text-sm text-rose-700">Patient not found.</p>;

  return (
    <div className="space-y-6">
      {error ? <div className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{error}</div> : null}

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
          One chart, multiple services. Enrollment and notes remain service-scoped.
        </TabsContent>

        <TabsContent value="services" className="pt-4">
          <Card className="border-slate-200/70 shadow-sm">
            <CardHeader><CardTitle className="text-base">Service Enrollments</CardTitle></CardHeader>
            <CardContent className="space-y-4 pt-0">
              <form className="grid gap-2 sm:grid-cols-[1fr_auto_auto]" onSubmit={createEnrollment}>
                <select className="h-9 rounded-md border border-slate-200 px-3 text-sm" value={enrollmentServiceId} onChange={(e) => setEnrollmentServiceId(e.target.value)}>
                  {services.map((service) => <option key={service.id} value={service.id}>{service.code} - {service.name}</option>)}
                </select>
                <Input type="date" value={enrollmentStartDate} onChange={(e) => setEnrollmentStartDate(e.target.value)} />
                <Button type="submit">Enroll</Button>
              </form>
              <div className="space-y-2">
                {enrollments.map((enrollment) => (
                  <div key={enrollment.id} className="rounded-md border border-slate-200 p-3 text-sm">
                    <div className="font-semibold text-slate-900">{enrollment.service.name} ({enrollment.service.code})</div>
                    <div className="text-slate-600">Status: {enrollment.status} | {enrollment.start_date} to {enrollment.end_date || "open"}</div>
                    <div className="text-slate-500">Reporting: {enrollment.reporting_enabled ? "enabled" : "disabled"}</div>
                  </div>
                ))}
                {enrollments.length === 0 ? <div className="text-sm text-slate-600">No enrollments yet.</div> : null}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="notes" className="pt-4">
          <Card className="border-slate-200/70 shadow-sm">
            <CardHeader><CardTitle className="text-base">Service-Scoped Notes</CardTitle></CardHeader>
            <CardContent className="space-y-4 pt-0">
              <div className="flex flex-wrap gap-2">
                <Button type="button" size="sm" variant={noteServiceFilter === "all" ? "default" : "outline"} onClick={() => setNoteServiceFilter("all")}>All</Button>
                {Array.from(new Map(enrollments.map((e) => [e.service.id, e.service])).values()).map((service) => (
                  <Button key={service.id} type="button" size="sm" variant={noteServiceFilter === service.id ? "default" : "outline"} onClick={() => setNoteServiceFilter(service.id)}>
                    {service.code}
                  </Button>
                ))}
              </div>
              <form className="grid gap-2" onSubmit={createNote}>
                <div className="grid gap-2 sm:grid-cols-2">
                  <select className="h-9 rounded-md border border-slate-200 px-3 text-sm" value={noteServiceId} onChange={(e) => setNoteServiceId(e.target.value)}>
                    {Array.from(new Map(enrollments.map((e) => [e.service.id, e.service])).values()).map((service) => (
                      <option key={service.id} value={service.id}>{service.code} - {service.name}</option>
                    ))}
                  </select>
                  <select className="h-9 rounded-md border border-slate-200 px-3 text-sm" value={noteVisibility} onChange={(e) => setNoteVisibility(e.target.value as PatientNote["visibility"])}>
                    <option value="clinical_only">clinical_only</option>
                    <option value="legal_and_clinical">legal_and_clinical</option>
                  </select>
                </div>
                <textarea className="min-h-[96px] rounded-md border border-slate-200 px-3 py-2 text-sm" value={noteBody} onChange={(e) => setNoteBody(e.target.value)} />
                <Button type="submit">Add Note</Button>
              </form>
              <div className="space-y-2">
                {notes.map((note) => (
                  <div key={note.id} className="rounded-md border border-slate-200 p-3 text-sm">
                    <div className="flex flex-wrap gap-2">
                      <Badge className="border-cyan-200 bg-cyan-50 font-mono text-cyan-700">{note.primary_service.code}</Badge>
                      <Badge className="border-violet-200 bg-violet-50 text-violet-700">{note.visibility}</Badge>
                    </div>
                    <div className="mt-2 whitespace-pre-wrap text-slate-700">{note.body}</div>
                  </div>
                ))}
                {notes.length === 0 ? <div className="text-sm text-slate-600">No notes in this filter.</div> : null}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="documents" className="pt-4 text-sm text-slate-600">Documents placeholder.</TabsContent>
        <TabsContent value="compliance" className="pt-4 text-sm text-slate-600">Compliance placeholder.</TabsContent>
      </Tabs>
    </div>
  );
}
