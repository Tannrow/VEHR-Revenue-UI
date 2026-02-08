"use client";

import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import MetricCard from "../_components/MetricCard";
import { apiFetch } from "@/lib/api";

type ConnectorCapability = {
  key: string;
  label: string;
  description: string;
};

type Connector = {
  key: string;
  display_name: string;
  category: string;
  auth_modes: string[];
  capabilities: ConnectorCapability[];
};

type ConnectorCatalog = {
  total: number;
  categories: string[];
  connectors: Connector[];
};

export default function IntegrationsPage() {
  const [catalog, setCatalog] = useState<ConnectorCatalog | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;

    async function load() {
      try {
        setError(null);
        const data = await apiFetch<ConnectorCatalog>("/api/v1/integrations/connectors", {
          cache: "no-store",
        });
        if (!isMounted) return;
        setCatalog(data);
      } catch (err) {
        if (!isMounted) return;
        setError(err instanceof Error ? err.message : "Failed to load connector catalog");
      }
    }

    load();
    return () => {
      isMounted = false;
    };
  }, []);

  const connectors = catalog?.connectors ?? [];

  return (
    <div className="flex flex-col gap-6">
      <div className="space-y-2">
        <p className="text-[11px] font-semibold uppercase tracking-[0.32em] text-slate-400">
          Integration Hub
        </p>
        <h1 className="text-3xl font-semibold tracking-tight text-slate-900">Integration Catalog</h1>
        <p className="text-sm text-slate-500">
          Provider-agnostic connectors for storage, messaging, telephony, accounting, and identity.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <MetricCard label="Connectors" value={`${catalog?.total ?? 0}`} hint="Available adapters" />
        <MetricCard
          label="Categories"
          value={`${catalog?.categories.length ?? 0}`}
          hint="Integration domains"
        />
        <MetricCard
          label="Framework"
          value="Active"
          hint="Discovery + mapping preview live"
        />
      </div>

      {error ? (
        <Card className="border-rose-200 bg-rose-50/80">
          <CardContent className="pt-6 text-sm text-rose-700">{error}</CardContent>
        </Card>
      ) : null}

      <Card className="border-slate-200/70 shadow-sm">
        <CardHeader className="border-b border-slate-200/70 bg-slate-50/70">
          <CardTitle className="text-base text-slate-900">Categories</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2 pt-5">
          {(catalog?.categories ?? []).map((category) => (
            <Badge key={category} variant="outline" className="rounded-full border-slate-300 px-3 py-1 text-xs">
              {category.replace("_", " ")}
            </Badge>
          ))}
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        {connectors.map((connector) => (
          <Card key={connector.key} className="border-slate-200/70 shadow-sm">
            <CardHeader className="border-b border-slate-200/70 bg-slate-50/70">
              <div className="flex items-center justify-between gap-3">
                <CardTitle className="text-base text-slate-900">{connector.display_name}</CardTitle>
                <Badge variant="secondary" className="text-[10px] uppercase tracking-[0.2em]">
                  {connector.category.replace("_", " ")}
                </Badge>
              </div>
            </CardHeader>
            <CardContent className="space-y-4 pt-5">
              <div className="flex flex-wrap gap-2">
                {connector.auth_modes.map((mode) => (
                  <Badge key={`${connector.key}-${mode}`} variant="outline" className="text-[10px] uppercase">
                    {mode}
                  </Badge>
                ))}
              </div>
              <div className="space-y-3">
                {connector.capabilities.map((capability) => (
                  <div key={capability.key} className="rounded-xl border border-slate-200 bg-white px-3 py-2">
                    <div className="text-sm font-semibold text-slate-800">{capability.label}</div>
                    <div className="text-xs text-slate-500">{capability.description}</div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
