"use client";

import { useEffect, useMemo, useState } from "react";

import { ApiError, apiFetch } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type TeamMember = {
  id: string;
  full_name?: string | null;
  email: string;
  role: string;
  role_label: string;
};

type TeamRow = {
  name: string;
  members: TeamMember[];
};

function toMessage(error: unknown, fallback: string) {
  if (error instanceof ApiError || error instanceof Error) {
    return error.message || fallback;
  }
  return fallback;
}

export default function StaffPage() {
  const [teams, setTeams] = useState<TeamRow[]>([]);
  const [activeTeam, setActiveTeam] = useState<string>("");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;

    async function loadTeams() {
      setIsLoading(true);
      setError(null);
      try {
        const response = await apiFetch<TeamRow[]>("/api/v1/staff/teams", {
          cache: "no-store",
        });
        if (!isMounted) return;
        setTeams(response);
        if (response[0]) {
          setActiveTeam(response[0].name);
        }
      } catch (loadError) {
        if (!isMounted) return;
        setError(toMessage(loadError, "Unable to load teams."));
      } finally {
        if (isMounted) {
          setIsLoading(false);
        }
      }
    }

    void loadTeams();
    return () => {
      isMounted = false;
    };
  }, []);

  const selectedTeam = useMemo(
    () => teams.find((team) => team.name === activeTeam) ?? null,
    [teams, activeTeam],
  );

  return (
    <div className="flex flex-col gap-8">
      <div className="space-y-3">
        <p className="text-sm font-semibold text-slate-500">People</p>
        <h1 className="text-[2rem] font-semibold tracking-tight text-slate-900">Staff</h1>
        <p className="max-w-2xl text-base leading-7 text-slate-600">
          Team-based staffing view for admissions, clinical, billing, compliance, reception, and workforce.
        </p>
      </div>

      {isLoading ? <p className="text-sm text-slate-600">Loading teams...</p> : null}
      {error ? <p className="text-sm text-rose-700">{error}</p> : null}

      {!isLoading && !error ? (
        <div className="grid gap-5 xl:grid-cols-[280px_1fr]">
          <Card className="bg-white shadow-sm">
            <CardHeader className="pb-2">
              <CardTitle className="text-xl text-slate-900">Teams</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 pt-0">
              {teams.map((team) => (
                <button
                  key={team.name}
                  type="button"
                  onClick={() => setActiveTeam(team.name)}
                  className={`w-full rounded-lg px-3 py-2 text-left transition-colors ${
                    activeTeam === team.name
                      ? "bg-blue-50 text-blue-900"
                      : "bg-slate-50 text-slate-800 hover:bg-slate-100"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-semibold">{team.name}</span>
                    <span className="text-xs text-slate-500">{team.members.length}</span>
                  </div>
                </button>
              ))}
            </CardContent>
          </Card>

          <Card className="bg-white shadow-sm">
            <CardHeader className="pb-2">
              <CardTitle className="text-xl text-slate-900">
                {selectedTeam?.name || "Members"}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 pt-0">
              {selectedTeam?.members.length ? (
                selectedTeam.members.map((member) => (
                  <div key={member.id} className="rounded-lg bg-slate-50 px-4 py-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="text-sm font-semibold text-slate-900">{member.full_name || member.email}</p>
                      <span className="rounded-md border px-2 py-0.5 text-xs text-slate-600">
                        {member.role_label}
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-slate-500">{member.email}</p>
                  </div>
                ))
              ) : (
                <p className="text-sm text-slate-500">No members in this team.</p>
              )}
            </CardContent>
          </Card>
        </div>
      ) : null}
    </div>
  );
}
