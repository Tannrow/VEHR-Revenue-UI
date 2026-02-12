"use client";

import { useEffect, useState } from "react";

import { getBrowserAccessToken } from "@/lib/auth";
import { apiFetch, buildUrl } from "@/lib/api";

type CallRow = {
  call_id: string;
  state: string;
  overlay_status?: string | null;
  notes?: string | null;
};

type SnapshotResponse = {
  liveCalls?: CallRow[];
  call_log?: CallRow[];
  dispositions?: Array<{
    call_id: string;
    status: string;
    notes?: string | null;
  }>;
  presence?: unknown[];
};

type CallEventPayload = {
  call_id: string;
  state: string;
  overlay_status?: string;
  notes?: string | null;
};

type DispositionEventPayload = {
  call_id: string;
  status: string;
  notes?: string | null;
};

function upsertCall(calls: CallRow[], incoming: Partial<CallRow> & { call_id: string }): CallRow[] {
  const existing = calls.find((item) => item.call_id === incoming.call_id);
  const merged: CallRow = {
    call_id: incoming.call_id,
    state: incoming.state ?? existing?.state ?? "unknown",
    overlay_status: incoming.overlay_status ?? existing?.overlay_status ?? null,
    notes: incoming.notes ?? existing?.notes ?? null,
  };
  const withoutCurrent = calls.filter((item) => item.call_id !== incoming.call_id);
  return [merged, ...withoutCurrent];
}

export default function CallCenterTestPage() {
  const [calls, setCalls] = useState<CallRow[]>([]);
  const [streamState, setStreamState] = useState("offline");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    async function loadSnapshot() {
      try {
        const snapshot = await apiFetch<SnapshotResponse>("/api/v1/call-center/snapshot", {
          cache: "no-store",
        });
        if (!active) return;
        const baseCalls = snapshot.liveCalls ?? snapshot.call_log ?? [];
        const notesByCallId = new Map<string, string | null>();
        for (const row of snapshot.dispositions ?? []) {
          notesByCallId.set(row.call_id, row.notes ?? null);
        }
        setCalls(
          baseCalls.map((row) => ({
            ...row,
            notes: row.notes ?? notesByCallId.get(row.call_id) ?? null,
          })),
        );
        console.log("call-center-test:snapshot", snapshot);
      } catch (snapshotError) {
        if (!active) return;
        setError(snapshotError instanceof Error ? snapshotError.message : "Failed to load snapshot.");
      }
    }

    void loadSnapshot();

    const token = getBrowserAccessToken();
    if (!token) {
      return () => {
        active = false;
      };
    }

    const streamUrl = `${buildUrl("/api/v1/call-center/stream")}?access_token=${encodeURIComponent(token)}`;
    const source = new EventSource(streamUrl, { withCredentials: true });

    source.addEventListener("open", () => {
      setStreamState("connected");
    });

    source.addEventListener("call", (event) => {
      const payload = JSON.parse((event as MessageEvent).data) as CallEventPayload;
      console.log("call-center-test:event:call", payload);
      setCalls((current) =>
        upsertCall(current, {
          call_id: payload.call_id,
          state: payload.state,
          overlay_status: payload.overlay_status,
          notes: payload.notes,
        }),
      );
    });

    source.addEventListener("disposition", (event) => {
      const payload = JSON.parse((event as MessageEvent).data) as DispositionEventPayload;
      console.log("call-center-test:event:disposition", payload);
      setCalls((current) =>
        upsertCall(current, {
          call_id: payload.call_id,
          state: current.find((item) => item.call_id === payload.call_id)?.state ?? "unknown",
          overlay_status: payload.status,
          notes: payload.notes,
        }),
      );
    });

    source.addEventListener("presence", (event) => {
      console.log("call-center-test:event:presence", JSON.parse((event as MessageEvent).data));
    });

    source.addEventListener("snapshot", (event) => {
      const payload = JSON.parse((event as MessageEvent).data) as SnapshotResponse;
      console.log("call-center-test:event:snapshot", payload);
      const baseCalls = payload.liveCalls ?? payload.call_log ?? [];
      setCalls(baseCalls);
    });

    source.onerror = () => {
      setStreamState("reconnecting");
    };

    return () => {
      active = false;
      source.close();
      setStreamState("offline");
    };
  }, []);

  return (
    <div>
      <h1>Call Center Test</h1>
      <p>Stream: {streamState}</p>
      {error ? <p>{error}</p> : null}
      <ul>
        {calls.map((row) => (
          <li key={row.call_id}>
            {row.call_id} | state={row.state} | missed={row.overlay_status === "MISSED" ? "yes" : "no"} | notes={row.notes || ""}
          </li>
        ))}
      </ul>
    </div>
  );
}
