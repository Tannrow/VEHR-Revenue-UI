"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ExternalLink } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import MetricCard from "../_components/MetricCard";
import { ApiError, apiFetch, buildUrl } from "@/lib/api";

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

type MicrosoftConnectResponse = {
  authorization_url: string;
};

type RingCentralStatus = {
  connected: boolean;
  rc_account_id?: string | null;
  rc_extension_id?: string | null;
  expires_at?: string | null;
};

export default function IntegrationsPage() {
  const searchParams = useSearchParams();
  const [catalog, setCatalog] = useState<ConnectorCatalog | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isConnectingMicrosoft, setIsConnectingMicrosoft] = useState(false);
  const [microsoftConnectError, setMicrosoftConnectError] = useState<string | null>(null);
  const [ringCentralStatus, setRingCentralStatus] = useState<RingCentralStatus | null>(null);
  const [isConnectingRingCentral, setIsConnectingRingCentral] = useState(false);
  const [ringCentralError, setRingCentralError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;

    async function load() {
      try {
        setError(null);
        const [data, status] = await Promise.all([
          apiFetch<ConnectorCatalog>("/api/v1/integrations/connectors", {
            cache: "no-store",
          }),
          apiFetch<RingCentralStatus>("/api/v1/integrations/ringcentral/status", {
            cache: "no-store",
          }),
        ]);
        if (!isMounted) return;
        setCatalog(data);
        setRingCentralStatus(status);
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

  useEffect(() => {
    const connected = searchParams.get("connected");
    const err = searchParams.get("err");
    if (connected === "1") {
      setRingCentralError(null);
      return;
    }
    if (connected === "0") {
      setRingCentralError(err ? `RingCentral OAuth failed (${err}).` : "RingCentral OAuth failed.");
    }
  }, [searchParams]);

  const connectors = catalog?.connectors ?? [];

  async function handleConnectMicrosoft() {
    setMicrosoftConnectError(null);
    setIsConnectingMicrosoft(true);
    try {
      const response = await apiFetch<MicrosoftConnectResponse>(
        "/api/v1/integrations/microsoft/connect",
        { cache: "no-store" },
      );
      if (!response.authorization_url) {
        throw new Error("Microsoft authorization URL was not returned.");
      }
      window.location.assign(response.authorization_url);
    } catch (connectError) {
      if (connectError instanceof ApiError || connectError instanceof Error) {
        setMicrosoftConnectError(connectError.message || "Unable to start Microsoft connection.");
      } else {
        setMicrosoftConnectError("Unable to start Microsoft connection.");
      }
      setIsConnectingMicrosoft(false);
    }
  }

  async function handleConnectRingCentral() {
    setRingCentralError(null);
    setIsConnectingRingCentral(true);
    try {
      const returnTo = `${window.location.origin}/integrations`;
      const connectUrl = `${buildUrl("/api/v1/integrations/ringcentral/connect")}?return_to=${encodeURIComponent(returnTo)}`;
      window.location.assign(connectUrl);
    } catch (connectError) {
      if (connectError instanceof ApiError || connectError instanceof Error) {
        setRingCentralError(connectError.message || "Unable to start RingCentral connection.");
      } else {
        setRingCentralError("Unable to start RingCentral connection.");
      }
      setIsConnectingRingCentral(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-2">
          <p className="text-[11px] font-semibold uppercase tracking-[0.32em] text-slate-400">
            Integration Hub
          </p>
          <h1 className="text-3xl font-semibold tracking-tight text-slate-900">Integration Catalog</h1>
          <p className="text-sm text-slate-600">
            Provider-agnostic connectors for storage, messaging, telephony, accounting, and identity.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button type="button" onClick={handleConnectRingCentral} disabled={isConnectingRingCentral}>
            {isConnectingRingCentral ? "Redirecting..." : "Connect RingCentral"}
            <ExternalLink className="h-4 w-4" />
          </Button>
          <Button type="button" variant="outline" onClick={handleConnectMicrosoft} disabled={isConnectingMicrosoft}>
            {isConnectingMicrosoft ? "Redirecting..." : "Connect Microsoft"}
            <ExternalLink className="h-4 w-4" />
          </Button>
        </div>
      </div>

      <Card className="border-slate-200/70 shadow-sm">
        <CardHeader className="border-b border-slate-200/70 bg-slate-50/70">
          <CardTitle className="text-base text-slate-900">RingCentral OAuth</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 pt-5 text-sm text-slate-700">
          <p>Status: {ringCentralStatus?.connected ? "Connected" : "Not connected"}</p>
          <p>Account: {ringCentralStatus?.rc_account_id || "n/a"}</p>
          <p>Extension: {ringCentralStatus?.rc_extension_id || "n/a"}</p>
          <p>Expires: {ringCentralStatus?.expires_at ? new Date(ringCentralStatus.expires_at).toLocaleString() : "n/a"}</p>
        </CardContent>
      </Card>

      {microsoftConnectError ? (
        <Card className="border-rose-200 bg-rose-50/80">
          <CardContent className="pt-6 text-sm text-rose-700">{microsoftConnectError}</CardContent>
        </Card>
      ) : null}
      {ringCentralError ? (
        <Card className="border-rose-200 bg-rose-50/80">
          <CardContent className="pt-6 text-sm text-rose-700">{ringCentralError}</CardContent>
        </Card>
      ) : null}

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
              {connector.key === "sharepoint" ? (
                <Button
                  type="button"
                  variant="outline"
                  className="w-full justify-center"
                  onClick={handleConnectMicrosoft}
                  disabled={isConnectingMicrosoft}
                >
                  {isConnectingMicrosoft ? "Redirecting..." : "Connect Microsoft"}
                  <ExternalLink className="h-4 w-4" />
                </Button>
              ) : null}
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
