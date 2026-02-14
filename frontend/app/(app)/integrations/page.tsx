"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";

import { IntegrationStatusCard } from "@/components/enterprise/integration-status-card";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ApiError, apiFetch, buildUrl } from "@/lib/api";
import { AppLayoutPageConfig } from "@/lib/app-layout-config";

type MicrosoftConnectResponse = {
  authorization_url: string;
};

type MicrosoftConnectionTestResponse = {
  display_name?: string | null;
  user_principal_name?: string | null;
};

type RingCentralStatus = {
  connected: boolean;
};

export default function IntegrationsPage() {
  const searchParams = useSearchParams();
  const [pageError, setPageError] = useState<string | null>(null);
  const [ringCentralStatus, setRingCentralStatus] = useState<RingCentralStatus | null>(null);
  const [microsoftConnected, setMicrosoftConnected] = useState(false);
  const [isConnectingMicrosoft, setIsConnectingMicrosoft] = useState(false);
  const [microsoftConnectError, setMicrosoftConnectError] = useState<string | null>(null);
  const [isConnectingRingCentral, setIsConnectingRingCentral] = useState(false);
  const [isDisconnectingRingCentral, setIsDisconnectingRingCentral] = useState(false);
  const [ringCentralError, setRingCentralError] = useState<string | null>(null);

  const loadMicrosoftConnectionStatus = useCallback(async (): Promise<boolean> => {
    try {
      await apiFetch<MicrosoftConnectionTestResponse>("/api/v1/integrations/microsoft/test", {
        method: "POST",
        cache: "no-store",
      });
      return true;
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        return false;
      }
      throw err;
    }
  }, []);

  const refreshStatuses = useCallback(async () => {
    setPageError(null);
    try {
      const [ringCentral, microsoft] = await Promise.all([
        apiFetch<RingCentralStatus>("/api/v1/integrations/ringcentral/status", {
          cache: "no-store",
        }),
        loadMicrosoftConnectionStatus(),
      ]);
      setRingCentralStatus(ringCentral);
      setMicrosoftConnected(microsoft);
    } catch (err) {
      setPageError(err instanceof Error ? err.message : "Failed to load integration status.");
    }
  }, [loadMicrosoftConnectionStatus]);

  useEffect(() => {
    void refreshStatuses();
  }, [refreshStatuses]);

  useEffect(() => {
    const connected = searchParams.get("connected");
    if (connected === "1") {
      setRingCentralError(null);
      setRingCentralStatus({ connected: true });
      return;
    }
    if (connected === "0") {
      setRingCentralError("RingCentral connection could not be completed. Please try again.");
    }
  }, [searchParams]);

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
    } catch (err) {
      setMicrosoftConnectError("Unable to start Microsoft connection.");
      if (err instanceof Error) {
        setPageError(err.message);
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
    } catch {
      setRingCentralError("Unable to start RingCentral connection.");
      setIsConnectingRingCentral(false);
    }
  }

  async function handleDisconnectRingCentral() {
    setRingCentralError(null);
    setIsDisconnectingRingCentral(true);
    try {
      await apiFetch("/api/v1/integrations/ringcentral/disconnect", { method: "POST" });
      setRingCentralStatus({ connected: false });
    } catch (err) {
      setRingCentralError(err instanceof Error ? err.message : "Unable to disconnect RingCentral.");
    } finally {
      setIsDisconnectingRingCentral(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <AppLayoutPageConfig
        moduleLabel="System"
        pageTitle="Integrations"
        subtitle="Manage organization integrations in a simplified status view."
      />

      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-2">
          <h1 className="text-3xl font-semibold tracking-tight text-slate-900">Connected Systems</h1>
          <p className="text-sm text-slate-600">
            Connect or disconnect core external systems.
          </p>
        </div>
        <Button type="button" variant="outline" size="sm" onClick={() => void refreshStatuses()}>
          Refresh status
        </Button>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <IntegrationStatusCard
          title="RingCentral"
          provider="ringcentral"
          connected={Boolean(ringCentralStatus?.connected)}
          onConnect={() => void handleConnectRingCentral()}
          isConnecting={isConnectingRingCentral}
          connectLabel="Connect RingCentral"
          onDisconnect={() => void handleDisconnectRingCentral()}
          isDisconnecting={isDisconnectingRingCentral}
          message={ringCentralError}
        />

        <IntegrationStatusCard
          title="Microsoft SharePoint"
          provider="sharepoint"
          connected={microsoftConnected}
          onConnect={() => void handleConnectMicrosoft()}
          isConnecting={isConnectingMicrosoft}
          connectLabel="Connect Microsoft"
          message={microsoftConnectError}
          secondaryAction={(
            <Button type="button" variant="outline" size="sm" asChild>
              <Link href="/sharepoint">Open Organization Information</Link>
            </Button>
          )}
        />
      </div>

      {pageError ? (
        <Card className="border-rose-200 bg-rose-50/80">
          <CardContent className="pt-6 text-sm text-rose-700">{pageError}</CardContent>
        </Card>
      ) : null}
    </div>
  );
}
