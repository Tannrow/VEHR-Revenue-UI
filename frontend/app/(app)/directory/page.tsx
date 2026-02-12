"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { ApiError } from "@/lib/api";
import { ModuleId, defaultRouteForModule, getModuleById, isModuleId } from "@/lib/modules";
import { fetchMePreferences, patchMePreferences } from "@/lib/preferences";

const TILE_STYLES: Record<ModuleId, string> = {
  care_delivery: "from-cyan-500/20 to-cyan-200/10 border-cyan-200",
  call_center: "from-emerald-500/20 to-emerald-200/10 border-emerald-200",
  workforce: "from-amber-500/20 to-amber-200/10 border-amber-200",
  revenue_cycle: "from-slate-500/20 to-slate-200/10 border-slate-300",
  governance: "from-rose-500/20 to-rose-200/10 border-rose-200",
  administration: "from-indigo-500/20 to-indigo-200/10 border-indigo-200",
};

const TILE_ICONS: Record<ModuleId, string> = {
  care_delivery: "CD",
  call_center: "CC",
  workforce: "WM",
  revenue_cycle: "RC",
  governance: "GV",
  administration: "AD",
};

export default function DirectoryPage() {
  const router = useRouter();
  const [allowedModules, setAllowedModules] = useState<ModuleId[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [launchingModule, setLaunchingModule] = useState<ModuleId | null>(null);

  useEffect(() => {
    let isMounted = true;

    async function load() {
      try {
        setLoading(true);
        setError(null);
        const preferences = await fetchMePreferences();
        if (!isMounted) return;
        const normalized = preferences.allowed_modules.filter((id): id is ModuleId => isModuleId(id));
        setAllowedModules(normalized);
      } catch (loadError) {
        if (!isMounted) return;
        if (loadError instanceof ApiError || loadError instanceof Error) {
          setError(loadError.message);
        } else {
          setError("Failed to load organizational directory");
        }
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    }

    load();
    return () => {
      isMounted = false;
    };
  }, []);

  const visibleTiles = useMemo(() => {
    return allowedModules.map((moduleId) => getModuleById(moduleId));
  }, [allowedModules]);

  async function enterModule(moduleId: ModuleId) {
    try {
      setLaunchingModule(moduleId);
      await patchMePreferences({ last_active_module: moduleId });
      router.push(defaultRouteForModule(moduleId));
    } catch (launchError) {
      if (launchError instanceof ApiError || launchError instanceof Error) {
        setError(launchError.message);
      } else {
        setError("Failed to enter module");
      }
    } finally {
      setLaunchingModule(null);
    }
  }

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6">
      <div className="rounded-2xl border border-slate-200 bg-gradient-to-br from-slate-50 to-white px-6 py-6 shadow-sm">
        <h1 className="text-3xl font-semibold tracking-tight text-slate-900">Organizational Directory</h1>
        <p className="mt-2 text-sm text-slate-600">Select a system zone to launch a focused module workspace.</p>
      </div>

      {error ? (
        <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>
      ) : null}

      {loading ? (
        <div className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600">Loading modules...</div>
      ) : null}

      {!loading && visibleTiles.length === 0 ? (
        <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          No modules are currently available for your role in this organization.
        </div>
      ) : null}

      {!loading && visibleTiles.length > 0 ? (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {visibleTiles.map((tile) => (
            <button
              key={tile.id}
              type="button"
              onClick={() => enterModule(tile.id)}
              className={`group relative overflow-hidden rounded-2xl border bg-gradient-to-br p-6 text-left shadow-sm transition-all duration-200 hover:-translate-y-1 hover:shadow-lg ${TILE_STYLES[tile.id]}`}
            >
              <div className="absolute inset-0 bg-white/45 transition-opacity duration-200 group-hover:opacity-25" />
              <div className="relative z-10 flex items-start gap-4">
                <span className="inline-flex h-14 w-14 shrink-0 items-center justify-center rounded-xl border border-white/70 bg-white/70 text-sm font-bold tracking-[0.2em] text-slate-800">
                  {TILE_ICONS[tile.id]}
                </span>
                <span className="min-w-0">
                  <span className="block text-xl font-semibold tracking-tight text-slate-900">{tile.name}</span>
                  <span className="mt-1 block text-sm text-slate-700">{tile.description}</span>
                </span>
              </div>
              <div className="relative z-10 mt-6 text-xs font-semibold uppercase tracking-[0.16em] text-slate-700">
                {launchingModule === tile.id ? "Launching..." : "Enter Module"}
              </div>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
