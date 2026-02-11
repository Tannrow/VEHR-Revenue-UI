"use client";

import { useEffect, useState } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";

type ClientRecord = {
  id: string;
  first_name: string;
  last_name: string;
  dob?: string | null;
};

export default function ClientsPage() {
  const [clients, setClients] = useState<ClientRecord[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;

    async function loadClients() {
      try {
        setError(null);
        const data = await apiFetch<ClientRecord[]>("/api/v1/patients", { cache: "no-store" });
        if (!isMounted) return;
        setClients(data);
      } catch (loadError) {
        if (!isMounted) return;
        setError(loadError instanceof Error ? loadError.message : "Unable to load client records.");
      }
    }

    void loadClients();
    return () => {
      isMounted = false;
    };
  }, []);

  return (
    <div className="flex flex-col gap-6">
      <div className="space-y-3">
        <p className="text-[11px] font-semibold uppercase tracking-[0.32em] text-slate-400">Encompass 360</p>
        <h1 className="text-[2rem] font-semibold tracking-tight text-slate-900">Clients</h1>
        <p className="text-sm text-slate-500">CRM-style directory of active client relationships.</p>
      </div>

      {error ? <p className="text-sm text-rose-700">{error}</p> : null}

      <Card className="bg-white shadow-sm">
        <CardHeader className="pb-3">
          <CardTitle className="text-lg text-slate-900">Client Directory</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 pt-0">
          {clients.length === 0 ? (
            <p className="text-sm text-slate-500">No active clients found.</p>
          ) : (
            clients.map((client) => (
              <div key={client.id} className="rounded-lg bg-slate-50 px-4 py-3">
                <p className="text-sm font-semibold text-slate-900">
                  {client.last_name}, {client.first_name}
                </p>
                <div className="mt-1 flex flex-wrap gap-3 text-xs text-slate-500">
                  <span>DOB: {client.dob || "\u2014"}</span>
                  <span>ID: {client.id}</span>
                </div>
              </div>
            ))
          )}
        </CardContent>
      </Card>
    </div>
  );
}
