"use client";

import { useEffect, useState } from "react";
import {
  AlertTriangle,
  Copy,
  ExternalLink,
  FileText,
  FolderOpen,
  GraduationCap,
  LayoutTemplate,
  ScrollText,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";

type QuickLink = {
  label: string;
  url: string;
  description?: string | null;
};

type SharePointSettingsResponse = {
  home_url: string;
  quick_links: QuickLink[];
};

const EMBED_TIMEOUT_MS = 8000;
const DEFAULT_SHAREPOINT_HOME_URL =
  "https://valleyhealthandcounseling.sharepoint.com/sites/ValleyHealthHomePage";
const DEFAULT_QUICK_LINKS: Array<Omit<QuickLink, "url">> = [
  { label: "Policies", description: "Organization policies and procedures" },
  { label: "Training", description: "Training resources and onboarding" },
  { label: "Templates", description: "Operational templates and examples" },
  { label: "Contracts", description: "Contract and vendor documents" },
  { label: "Forms", description: "Frequently used organizational forms" },
];
const QUICK_LINK_ICONS = [FileText, GraduationCap, LayoutTemplate, ScrollText, FolderOpen];

function buildDefaultQuickLinks(homeUrl: string): QuickLink[] {
  return DEFAULT_QUICK_LINKS.map((item) => ({
    label: item.label,
    description: item.description,
    url: homeUrl,
  }));
}

function normalizeQuickLinks(homeUrl: string, quickLinks: QuickLink[] | null | undefined): QuickLink[] {
  if (!quickLinks || quickLinks.length === 0) {
    return buildDefaultQuickLinks(homeUrl);
  }
  return quickLinks.map((link) => ({
    label: link.label,
    description: link.description ?? undefined,
    url: link.url,
  }));
}

function toErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return fallback;
}

export default function SharePointPage() {
  const [homeUrl, setHomeUrl] = useState<string>(DEFAULT_SHAREPOINT_HOME_URL);
  const [quickLinks, setQuickLinks] = useState<QuickLink[]>(
    buildDefaultQuickLinks(DEFAULT_SHAREPOINT_HOME_URL),
  );
  const [loadingSettings, setLoadingSettings] = useState(true);
  const [settingsNotice, setSettingsNotice] = useState<string | null>(null);
  const [copyStatus, setCopyStatus] = useState<"idle" | "copied" | "failed">("idle");
  const [showEmbedded, setShowEmbedded] = useState(false);
  const [iframeKey, setIframeKey] = useState(0);
  const [iframeLoading, setIframeLoading] = useState(false);
  const [iframeTimedOut, setIframeTimedOut] = useState(false);

  useEffect(() => {
    let mounted = true;
    async function loadSharePointSettings() {
      try {
        setLoadingSettings(true);
        setSettingsNotice(null);
        const response = await apiFetch<SharePointSettingsResponse>(
          "/api/v1/org/sharepoint-settings",
          { cache: "no-store" },
        );
        if (!mounted) return;
        setHomeUrl(response.home_url);
        setQuickLinks(normalizeQuickLinks(response.home_url, response.quick_links));
      } catch (error) {
        if (!mounted) return;
        setHomeUrl(DEFAULT_SHAREPOINT_HOME_URL);
        setQuickLinks(buildDefaultQuickLinks(DEFAULT_SHAREPOINT_HOME_URL));
        setSettingsNotice(toErrorMessage(error, "Using default SharePoint links right now."));
      } finally {
        if (mounted) {
          setLoadingSettings(false);
        }
      }
    }

    loadSharePointSettings();
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    if (!showEmbedded || !iframeLoading) {
      return;
    }

    const timer = window.setTimeout(() => {
      setIframeTimedOut(true);
      setIframeLoading(false);
    }, EMBED_TIMEOUT_MS);

    return () => {
      window.clearTimeout(timer);
    };
  }, [showEmbedded, iframeLoading, iframeKey]);

  async function handleCopyLink() {
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(homeUrl);
      } else {
        const textarea = document.createElement("textarea");
        textarea.value = homeUrl;
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        document.body.appendChild(textarea);
        textarea.focus();
        textarea.select();
        document.execCommand("copy");
        document.body.removeChild(textarea);
      }
      setCopyStatus("copied");
    } catch {
      setCopyStatus("failed");
    }
  }

  function handleTryEmbed() {
    if (showEmbedded) {
      setShowEmbedded(false);
      setIframeLoading(false);
      setIframeTimedOut(false);
      return;
    }
    setShowEmbedded(true);
    setIframeLoading(true);
    setIframeTimedOut(false);
    setIframeKey((current) => current + 1);
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="space-y-2 border-b border-slate-200/70 pb-4">
        <h1 className="text-3xl font-semibold tracking-tight text-slate-900">SharePoint</h1>
        <p className="text-sm text-slate-500">
          Open Valley Health &amp; Counseling SharePoint resources.
        </p>
      </div>

      <Card className="border-slate-200/70 shadow-sm">
        <CardHeader className="border-b border-slate-200/70 bg-slate-50/70">
          <CardTitle className="text-base text-slate-900">SharePoint</CardTitle>
        </CardHeader>
        <CardContent className="space-y-5 pt-5">
          <div className="rounded-xl border border-slate-200 bg-slate-50/90 p-4">
            <p className="text-sm font-semibold text-slate-900">Embedded views are blocked</p>
            <p className="mt-1 text-sm text-slate-600">
              Your organization&apos;s SharePoint blocks embedded views for security. Use the
              button below to open SharePoint in a new tab.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <Button asChild>
              <a href={homeUrl} target="_blank" rel="noopener noreferrer">
                Open SharePoint
                <ExternalLink className="h-4 w-4" />
              </a>
            </Button>
            <Button type="button" variant="outline" onClick={handleCopyLink}>
              Copy link
              <Copy className="h-4 w-4" />
            </Button>
            <button
              type="button"
              onClick={handleTryEmbed}
              className="text-sm font-semibold text-slate-600 underline decoration-slate-300 underline-offset-4 hover:text-slate-900"
            >
              {showEmbedded ? "Hide embedded view" : "Try embedded view"}
            </button>
          </div>

          {copyStatus === "copied" ? (
            <p className="text-xs font-medium text-emerald-700">Link copied to clipboard.</p>
          ) : null}
          {copyStatus === "failed" ? (
            <p className="text-xs font-medium text-amber-700">Unable to copy link. Please copy it manually.</p>
          ) : null}
          {settingsNotice ? <p className="text-xs text-slate-500">{settingsNotice}</p> : null}

          {showEmbedded ? (
            <div className="space-y-3 rounded-xl border border-slate-200 bg-white p-4">
              <div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                <span>Embedding may be blocked by policy.</span>
              </div>
              <div className="relative h-[28rem] overflow-hidden rounded-lg border border-slate-200 bg-slate-50">
                <iframe
                  key={iframeKey}
                  src={homeUrl}
                  title="SharePoint embedded preview"
                  className="h-full w-full border-0"
                  onLoad={() => setIframeLoading(false)}
                />
                {iframeLoading ? (
                  <div className="absolute inset-0 flex items-center justify-center bg-white/85">
                    <div className="flex items-center gap-3 rounded-full border border-slate-200 bg-white px-4 py-2 text-sm text-slate-700 shadow-sm">
                      <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-cyan-500" />
                      Loading embedded view...
                    </div>
                  </div>
                ) : null}
              </div>
              {iframeTimedOut ? (
                <p className="text-xs text-slate-600">
                  Embedded view did not load within 8 seconds. Open SharePoint in a new tab for the
                  most reliable experience.
                </p>
              ) : null}
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card className="border-slate-200/70 shadow-sm">
        <CardHeader className="border-b border-slate-200/70 bg-slate-50/70">
          <CardTitle className="text-base text-slate-900">Quick Links</CardTitle>
        </CardHeader>
        <CardContent className="pt-5">
          {loadingSettings ? (
            <div className="text-sm text-slate-500">Loading links...</div>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {quickLinks.map((link, index) => {
                const Icon = QUICK_LINK_ICONS[index % QUICK_LINK_ICONS.length];
                return (
                  <a
                    key={`${link.label}-${link.url}-${index}`}
                    href={link.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="group rounded-xl border border-slate-200 bg-white p-4 transition hover:border-cyan-300 hover:bg-cyan-50/30"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <span className="flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 bg-slate-50 text-slate-600 group-hover:border-cyan-200 group-hover:bg-cyan-50 group-hover:text-cyan-700">
                        <Icon className="h-4 w-4" />
                      </span>
                      <ExternalLink className="h-4 w-4 text-slate-400 group-hover:text-cyan-700" />
                    </div>
                    <p className="mt-3 text-sm font-semibold text-slate-900">{link.label}</p>
                    {link.description ? (
                      <p className="mt-1 text-xs text-slate-500">{link.description}</p>
                    ) : null}
                  </a>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
