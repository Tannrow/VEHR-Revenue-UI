"use client";

import type { ComponentType } from "react";
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  BadgeCheck,
  Beaker,
  BookOpen,
  Briefcase,
  FileSignature,
  FileText,
  GraduationCap,
  Layers,
  PhoneCall,
  ShieldCheck,
  Users,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";

type OrganizationTile = {
  id: string;
  title: string;
  icon: string;
  category: string;
  link_type: "internal_route" | "external_url";
  href: string;
  sort_order: number;
  required_permissions: string[];
  is_active: boolean;
};

type Announcement = {
  id: string;
  title: string;
  body: string;
  start_date: string;
  end_date?: string | null;
  is_active: boolean;
  created_at: string;
};

type WorkSummaryItem = {
  key: string;
  title: string;
  count: number;
  href: string;
};

type WorkSummary = {
  show_widget: boolean;
  items: WorkSummaryItem[];
};

type OrganizationHomeResponse = {
  tiles: OrganizationTile[];
  announcements: Announcement[];
};

const ICONS: Record<string, ComponentType<{ className?: string }>> = {
  beaker: Beaker,
  briefcase: Briefcase,
  "file-text": FileText,
  layers: Layers,
  "shield-check": ShieldCheck,
  "book-open": BookOpen,
  "alert-triangle": AlertTriangle,
  "badge-check": BadgeCheck,
  users: Users,
  "graduation-cap": GraduationCap,
  "phone-call": PhoneCall,
  "file-signature": FileSignature,
};

function toErrorMessage(error: unknown, fallback: string) {
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

export default function OrganizationHomePage() {
  const [tiles, setTiles] = useState<OrganizationTile[]>([]);
  const [announcements, setAnnouncements] = useState<Announcement[]>([]);
  const [workSummary, setWorkSummary] = useState<WorkSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    async function load() {
      try {
        setLoading(true);
        setError(null);
        const [home, work] = await Promise.all([
          apiFetch<OrganizationHomeResponse>("/api/v1/organization/home", { cache: "no-store" }),
          apiFetch<WorkSummary>("/api/v1/me/work-summary", { cache: "no-store" }),
        ]);
        if (!mounted) return;
        setTiles(home.tiles);
        setAnnouncements(home.announcements);
        setWorkSummary(work);
      } catch (loadError) {
        if (!mounted) return;
        setError(toErrorMessage(loadError, "Failed to load organization home"));
      } finally {
        if (mounted) setLoading(false);
      }
    }
    load();
    return () => {
      mounted = false;
    };
  }, []);

  const groupedTiles = useMemo(() => {
    const grouped = new Map<string, OrganizationTile[]>();
    for (const tile of tiles) {
      if (!grouped.has(tile.category)) grouped.set(tile.category, []);
      grouped.get(tile.category)?.push(tile);
    }
    return Array.from(grouped.entries()).map(([category, categoryTiles]) => ({
      category,
      tiles: [...categoryTiles].sort((a, b) => a.sort_order - b.sort_order),
    }));
  }, [tiles]);

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <p className="text-[11px] font-semibold uppercase tracking-[0.32em] text-slate-400">Organization</p>
        <h1 className="text-3xl font-semibold tracking-tight text-slate-900">Home</h1>
        <p className="text-sm text-slate-500">Operational hub for daily staff workflows.</p>
      </div>

      {error ? (
        <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>
      ) : null}

      <Card className="border-slate-200/70 shadow-sm">
        <CardHeader className="border-b border-slate-200/70 bg-slate-50/70">
          <CardTitle className="text-base">Announcements</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 pt-5">
          {loading ? <div className="text-sm text-slate-600">Loading announcements...</div> : null}
          {!loading && announcements.length === 0 ? (
            <div className="text-sm text-slate-600">No active announcements.</div>
          ) : null}
          {announcements.map((announcement) => (
            <div key={announcement.id} className="rounded-lg border border-slate-200 bg-white p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="text-sm font-semibold text-slate-900">{announcement.title}</div>
                <Badge className="border-slate-200 bg-slate-100 text-slate-700">
                  {announcement.start_date}
                  {announcement.end_date ? ` - ${announcement.end_date}` : ""}
                </Badge>
              </div>
              <div className="mt-2 whitespace-pre-wrap text-sm text-slate-700">{announcement.body}</div>
            </div>
          ))}
        </CardContent>
      </Card>

      {workSummary?.show_widget ? (
        <Card className="border-slate-200/70 shadow-sm">
          <CardHeader className="border-b border-slate-200/70 bg-slate-50/70">
            <CardTitle className="text-base">My Work</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3 pt-5 sm:grid-cols-2 xl:grid-cols-4">
            {workSummary.items.map((item) => (
              <Link
                key={item.key}
                href={item.href}
                className="rounded-lg border border-slate-200 bg-white p-4 transition hover:border-slate-300 hover:bg-slate-50"
              >
                <div className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">{item.title}</div>
                <div className="mt-2 text-2xl font-semibold text-slate-900">{item.count}</div>
              </Link>
            ))}
          </CardContent>
        </Card>
      ) : null}

      <div className="space-y-4">
        {groupedTiles.map((group) => (
          <Card key={group.category} className="border-slate-200/70 shadow-sm">
            <CardHeader className="border-b border-slate-200/70 bg-slate-50/70">
              <CardTitle className="text-base">{group.category}</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-3 pt-5 sm:grid-cols-2 xl:grid-cols-3">
              {group.tiles.map((tile) => {
                const Icon = ICONS[tile.icon] ?? Layers;
                const external = tile.link_type === "external_url";
                return (
                  <Link
                    key={tile.id}
                    href={tile.href}
                    target={external ? "_blank" : undefined}
                    rel={external ? "noopener noreferrer" : undefined}
                    className="rounded-lg border border-slate-200 bg-white p-4 transition hover:border-slate-300 hover:bg-slate-50"
                  >
                    <div className="flex items-center gap-3">
                      <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-slate-100 text-slate-700">
                        <Icon className="h-5 w-5" />
                      </span>
                      <div>
                        <div className="text-sm font-semibold text-slate-900">{tile.title}</div>
                        <div className="text-xs text-slate-500">{external ? "External" : "Internal"}</div>
                      </div>
                    </div>
                  </Link>
                );
              })}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
