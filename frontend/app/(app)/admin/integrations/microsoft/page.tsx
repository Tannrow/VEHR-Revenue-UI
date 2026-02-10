"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  CheckCircle2,
  ExternalLink,
  FileText,
  Folder,
  Image as ImageIcon,
  Link2,
  Search,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiError, apiFetch, apiFetchBlob } from "@/lib/api";

type MicrosoftConnectResponse = {
  authorization_url: string;
};

type MicrosoftConnectionTestResponse = {
  display_name?: string | null;
  user_principal_name?: string | null;
};

type SharePointSite = {
  id: string;
  name: string;
  web_url: string;
};

type SharePointDrive = {
  id: string;
  name: string;
  web_url: string;
};

type SharePointItem = {
  id: string;
  name: string;
  is_folder: boolean;
  size?: number | null;
  web_url: string;
  last_modified_date_time?: string | null;
  mime_type?: string | null;
};

type FolderCrumb = {
  id: string;
  name: string;
};

type PreviewKind = "none" | "pdf" | "image" | "external";

function formatBytes(size?: number | null): string {
  if (typeof size !== "number" || !Number.isFinite(size) || size < 0) {
    return "-";
  }
  if (size < 1024) {
    return `${size} B`;
  }
  if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(1)} KB`;
  }
  if (size < 1024 * 1024 * 1024) {
    return `${(size / (1024 * 1024)).toFixed(1)} MB`;
  }
  return `${(size / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

function isPdfFile(item: SharePointItem): boolean {
  const mime = (item.mime_type || "").toLowerCase();
  return mime === "application/pdf" || item.name.toLowerCase().endsWith(".pdf");
}

function isImageFile(item: SharePointItem): boolean {
  const mime = (item.mime_type || "").toLowerCase();
  return mime.startsWith("image/");
}

export default function MicrosoftIntegrationPage() {
  const searchParams = useSearchParams();
  const status = searchParams.get("status");
  const reason = searchParams.get("reason");

  const [isConnecting, setIsConnecting] = useState(false);
  const [connectError, setConnectError] = useState<string | null>(null);

  const [isTestingConnection, setIsTestingConnection] = useState(false);
  const [connectionState, setConnectionState] = useState<"unknown" | "connected" | "not_connected" | "error">(
    "unknown",
  );
  const [connectionMessage, setConnectionMessage] = useState<string | null>(null);
  const [connectionProfile, setConnectionProfile] = useState<MicrosoftConnectionTestResponse | null>(null);

  const [siteSearch, setSiteSearch] = useState("");
  const [isLoadingSites, setIsLoadingSites] = useState(false);
  const [sitesError, setSitesError] = useState<string | null>(null);
  const [sites, setSites] = useState<SharePointSite[]>([]);
  const [selectedSite, setSelectedSite] = useState<SharePointSite | null>(null);

  const [isLoadingDrives, setIsLoadingDrives] = useState(false);
  const [drivesError, setDrivesError] = useState<string | null>(null);
  const [drives, setDrives] = useState<SharePointDrive[]>([]);
  const [selectedDrive, setSelectedDrive] = useState<SharePointDrive | null>(null);

  const [isLoadingItems, setIsLoadingItems] = useState(false);
  const [itemsError, setItemsError] = useState<string | null>(null);
  const [items, setItems] = useState<SharePointItem[]>([]);
  const [folderStack, setFolderStack] = useState<FolderCrumb[]>([]);

  const [selectedFile, setSelectedFile] = useState<SharePointItem | null>(null);
  const [previewKind, setPreviewKind] = useState<PreviewKind>("none");
  const [isLoadingPreview, setIsLoadingPreview] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [previewBlobUrl, setPreviewBlobUrl] = useState<string | null>(null);

  useEffect(() => {
    return () => {
      if (previewBlobUrl) {
        URL.revokeObjectURL(previewBlobUrl);
      }
    };
  }, [previewBlobUrl]);

  async function handleConnectMicrosoft() {
    setConnectError(null);
    setIsConnecting(true);
    try {
      const response = await apiFetch<MicrosoftConnectResponse>(
        "/api/v1/integrations/microsoft/connect",
        { cache: "no-store" },
      );
      if (!response.authorization_url) {
        throw new Error("Microsoft authorization URL was not returned.");
      }
      window.location.assign(response.authorization_url);
    } catch (error) {
      if (error instanceof ApiError || error instanceof Error) {
        setConnectError(error.message || "Unable to start Microsoft connection.");
      } else {
        setConnectError("Unable to start Microsoft connection.");
      }
      setIsConnecting(false);
    }
  }

  async function testConnection() {
    setIsTestingConnection(true);
    setConnectionMessage(null);
    setConnectionProfile(null);
    try {
      const response = await apiFetch<MicrosoftConnectionTestResponse>(
        "/api/v1/integrations/microsoft/test",
        {
          method: "POST",
          cache: "no-store",
        },
      );
      setConnectionState("connected");
      setConnectionProfile(response);
      setConnectionMessage("Connected to Microsoft Graph.");
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        setConnectionState("not_connected");
        setConnectionMessage(error.message || "Microsoft is not connected.");
      } else if (error instanceof Error) {
        setConnectionState("error");
        setConnectionMessage(error.message || "Unable to test Microsoft connection.");
      } else {
        setConnectionState("error");
        setConnectionMessage("Unable to test Microsoft connection.");
      }
    } finally {
      setIsTestingConnection(false);
    }
  }

  useEffect(() => {
    void testConnection();
  }, []);

  async function loadDrives(site: SharePointSite) {
    setSelectedSite(site);
    setSelectedDrive(null);
    setDrives([]);
    setItems([]);
    setFolderStack([]);
    setSelectedFile(null);
    setPreviewKind("none");
    setPreviewError(null);

    setDrivesError(null);
    setIsLoadingDrives(true);
    try {
      const response = await apiFetch<SharePointDrive[]>(
        `/api/v1/sharepoint/sites/${encodeURIComponent(site.id)}/drives`,
        { cache: "no-store" },
      );
      setDrives(response);
    } catch (error) {
      setDrivesError(error instanceof Error ? error.message : "Unable to load drives.");
    } finally {
      setIsLoadingDrives(false);
    }
  }

  async function loadRootItems(drive: SharePointDrive) {
    setSelectedDrive(drive);
    setFolderStack([]);
    setSelectedFile(null);
    setPreviewKind("none");
    setPreviewError(null);
    setItemsError(null);
    setIsLoadingItems(true);
    try {
      const response = await apiFetch<SharePointItem[]>(
        `/api/v1/sharepoint/drives/${encodeURIComponent(drive.id)}/root/children`,
        { cache: "no-store" },
      );
      setItems(response);
    } catch (error) {
      setItemsError(error instanceof Error ? error.message : "Unable to load drive items.");
    } finally {
      setIsLoadingItems(false);
    }
  }

  async function loadFolderItems(crumbs: FolderCrumb[]) {
    if (!selectedDrive) return;

    setSelectedFile(null);
    setPreviewKind("none");
    setPreviewError(null);
    setItemsError(null);
    setIsLoadingItems(true);
    try {
      if (crumbs.length === 0) {
        const response = await apiFetch<SharePointItem[]>(
          `/api/v1/sharepoint/drives/${encodeURIComponent(selectedDrive.id)}/root/children`,
          { cache: "no-store" },
        );
        setFolderStack([]);
        setItems(response);
      } else {
        const active = crumbs[crumbs.length - 1];
        const response = await apiFetch<SharePointItem[]>(
          `/api/v1/sharepoint/drives/${encodeURIComponent(selectedDrive.id)}/items/${encodeURIComponent(active.id)}/children`,
          { cache: "no-store" },
        );
        setFolderStack(crumbs);
        setItems(response);
      }
    } catch (error) {
      setItemsError(error instanceof Error ? error.message : "Unable to load folder items.");
    } finally {
      setIsLoadingItems(false);
    }
  }

  async function searchSites() {
    const searchValue = siteSearch.trim();
    if (!searchValue) {
      setSites([]);
      return;
    }

    setSitesError(null);
    setIsLoadingSites(true);
    setSelectedSite(null);
    setSelectedDrive(null);
    setDrives([]);
    setItems([]);
    setFolderStack([]);
    setSelectedFile(null);
    setPreviewKind("none");
    setPreviewError(null);

    try {
      const response = await apiFetch<SharePointSite[]>(
        `/api/v1/sharepoint/sites?search=${encodeURIComponent(searchValue)}`,
        { cache: "no-store" },
      );
      setSites(response);
    } catch (error) {
      setSitesError(error instanceof Error ? error.message : "Unable to search SharePoint sites.");
    } finally {
      setIsLoadingSites(false);
    }
  }

  async function openFilePreview(item: SharePointItem) {
    setSelectedFile(item);
    setPreviewError(null);
    setPreviewKind("none");

    if (previewBlobUrl) {
      URL.revokeObjectURL(previewBlobUrl);
      setPreviewBlobUrl(null);
    }

    if (!selectedDrive) {
      setPreviewError("No drive is selected.");
      return;
    }

    const isPdf = isPdfFile(item);
    const isImage = isImageFile(item);
    if (!isPdf && !isImage) {
      setPreviewKind("external");
      return;
    }

    setIsLoadingPreview(true);
    try {
      const blob = await apiFetchBlob(
        `/api/v1/sharepoint/drives/${encodeURIComponent(selectedDrive.id)}/items/${encodeURIComponent(item.id)}/download`,
        { cache: "no-store" },
      );
      const objectUrl = URL.createObjectURL(blob);
      setPreviewBlobUrl(objectUrl);
      setPreviewKind(isPdf ? "pdf" : "image");
    } catch (error) {
      setPreviewKind("external");
      setPreviewError(error instanceof Error ? error.message : "Unable to preview file.");
    } finally {
      setIsLoadingPreview(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="space-y-2">
        <p className="text-[11px] font-semibold uppercase tracking-[0.32em] text-slate-400">
          Integration Hub
        </p>
        <h1 className="text-3xl font-semibold tracking-tight text-slate-900">Microsoft Graph</h1>
        <p className="text-sm text-slate-500">
          Connected SharePoint browsing without iframe embedding.
        </p>
      </div>

      {status === "connected" ? (
        <Card className="border-emerald-200 bg-emerald-50/70">
          <CardContent className="flex items-center gap-2 pt-6 text-sm font-medium text-emerald-800">
            <CheckCircle2 className="h-4 w-4" />
            Microsoft account connected successfully.
          </CardContent>
        </Card>
      ) : null}

      {status === "error" ? (
        <Card className="border-amber-200 bg-amber-50/70">
          <CardContent className="pt-6 text-sm text-amber-800">
            Microsoft connection could not be completed.
            {reason ? ` Reason: ${reason.replaceAll("_", " ")}.` : ""}
          </CardContent>
        </Card>
      ) : null}

      <Card className="border-slate-200/70 shadow-sm">
        <CardHeader className="border-b border-slate-200/70 bg-slate-50/70">
          <CardTitle className="text-base text-slate-900">Connection</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 pt-5">
          <div className="flex flex-wrap items-center gap-3">
            <Button type="button" onClick={handleConnectMicrosoft} disabled={isConnecting}>
              {isConnecting ? "Redirecting..." : "Connect Microsoft"}
              <ExternalLink className="h-4 w-4" />
            </Button>
            <Button type="button" variant="outline" onClick={testConnection} disabled={isTestingConnection}>
              {isTestingConnection ? "Testing..." : "Test Connection"}
            </Button>
          </div>

          <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700">
            Status:{" "}
            <span className="font-semibold">
              {connectionState === "connected"
                ? "Connected"
                : connectionState === "not_connected"
                  ? "Not connected"
                  : connectionState === "error"
                    ? "Error"
                    : "Checking"}
            </span>
            {connectionMessage ? <p className="mt-1 text-xs text-slate-600">{connectionMessage}</p> : null}
            {connectionProfile ? (
              <p className="mt-1 text-xs text-slate-600">
                {connectionProfile.display_name || "Unknown user"} ({connectionProfile.user_principal_name || "No UPN"})
              </p>
            ) : null}
          </div>

          {connectError ? <p className="text-sm text-rose-700">{connectError}</p> : null}
          <div className="flex items-start gap-2 rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs text-slate-600">
            <Link2 className="mt-0.5 h-4 w-4 shrink-0 text-slate-500" />
            <span>
              This starts an authenticated backend call, redirects to Microsoft consent, and returns
              here when complete.
            </span>
          </div>
        </CardContent>
      </Card>

      <Card className="border-slate-200/70 shadow-sm">
        <CardHeader className="border-b border-slate-200/70 bg-slate-50/70">
          <CardTitle className="text-base text-slate-900">SharePoint Browser</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 pt-5">
          <div className="flex flex-wrap gap-3">
            <Input
              value={siteSearch}
              onChange={(event) => setSiteSearch(event.target.value)}
              placeholder="Search SharePoint sites..."
              className="min-w-[280px] flex-1"
            />
            <Button type="button" variant="outline" onClick={searchSites} disabled={isLoadingSites}>
              <Search className="h-4 w-4" />
              {isLoadingSites ? "Searching..." : "Search Sites"}
            </Button>
          </div>
          {sitesError ? <p className="text-sm text-rose-700">{sitesError}</p> : null}

          <div className="grid gap-4 xl:grid-cols-[320px_1fr]">
            <div className="space-y-4">
              <Card className="border-slate-200/70">
                <CardHeader className="border-b border-slate-200/70 bg-slate-50/70 py-3">
                  <CardTitle className="text-sm text-slate-900">Sites</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2 pt-3">
                  {sites.length === 0 ? (
                    <p className="text-xs text-slate-500">Search to list available sites.</p>
                  ) : (
                    sites.map((site) => (
                      <button
                        key={site.id}
                        type="button"
                        onClick={() => loadDrives(site)}
                        className={`w-full rounded-lg border px-3 py-2 text-left text-sm transition ${
                          selectedSite?.id === site.id
                            ? "border-cyan-300 bg-cyan-50 text-cyan-900"
                            : "border-slate-200 bg-white text-slate-800 hover:border-slate-300"
                        }`}
                      >
                        <div className="font-semibold">{site.name}</div>
                        <div className="truncate text-xs text-slate-500">{site.web_url}</div>
                      </button>
                    ))
                  )}
                </CardContent>
              </Card>

              <Card className="border-slate-200/70">
                <CardHeader className="border-b border-slate-200/70 bg-slate-50/70 py-3">
                  <CardTitle className="text-sm text-slate-900">Drives</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2 pt-3">
                  {isLoadingDrives ? (
                    <p className="text-xs text-slate-500">Loading drives...</p>
                  ) : drives.length === 0 ? (
                    <p className="text-xs text-slate-500">Select a site to load drives.</p>
                  ) : (
                    drives.map((drive) => (
                      <button
                        key={drive.id}
                        type="button"
                        onClick={() => loadRootItems(drive)}
                        className={`w-full rounded-lg border px-3 py-2 text-left text-sm transition ${
                          selectedDrive?.id === drive.id
                            ? "border-cyan-300 bg-cyan-50 text-cyan-900"
                            : "border-slate-200 bg-white text-slate-800 hover:border-slate-300"
                        }`}
                      >
                        <div className="font-semibold">{drive.name}</div>
                        <div className="truncate text-xs text-slate-500">{drive.web_url}</div>
                      </button>
                    ))
                  )}
                  {drivesError ? <p className="text-xs text-rose-700">{drivesError}</p> : null}
                </CardContent>
              </Card>
            </div>

            <div className="space-y-4">
              <Card className="border-slate-200/70">
                <CardHeader className="border-b border-slate-200/70 bg-slate-50/70 py-3">
                  <CardTitle className="text-sm text-slate-900">Items</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3 pt-3">
                  <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
                    <button
                      type="button"
                      onClick={() => loadFolderItems([])}
                      disabled={!selectedDrive}
                      className="rounded border border-slate-200 bg-white px-2 py-1 hover:border-slate-300 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      Root
                    </button>
                    {folderStack.map((crumb, index) => (
                      <button
                        key={`${crumb.id}-${index}`}
                        type="button"
                        onClick={() => loadFolderItems(folderStack.slice(0, index + 1))}
                        className="rounded border border-slate-200 bg-white px-2 py-1 hover:border-slate-300"
                      >
                        {crumb.name}
                      </button>
                    ))}
                  </div>

                  {isLoadingItems ? (
                    <p className="text-xs text-slate-500">Loading items...</p>
                  ) : items.length === 0 ? (
                    <p className="text-xs text-slate-500">Select a drive to browse items.</p>
                  ) : (
                    <div className="space-y-2">
                      {items.map((item) => (
                        <div
                          key={item.id}
                          className={`flex items-center justify-between gap-3 rounded-lg border px-3 py-2 ${
                            selectedFile?.id === item.id
                              ? "border-cyan-300 bg-cyan-50"
                              : "border-slate-200 bg-white"
                          }`}
                        >
                          <button
                            type="button"
                            onClick={() => {
                              if (item.is_folder) {
                                void loadFolderItems([...folderStack, { id: item.id, name: item.name }]);
                                return;
                              }
                              void openFilePreview(item);
                            }}
                            className="flex min-w-0 flex-1 items-center gap-2 text-left"
                          >
                            {item.is_folder ? (
                              <Folder className="h-4 w-4 shrink-0 text-amber-600" />
                            ) : isImageFile(item) ? (
                              <ImageIcon className="h-4 w-4 shrink-0 text-cyan-600" />
                            ) : (
                              <FileText className="h-4 w-4 shrink-0 text-slate-500" />
                            )}
                            <span className="truncate text-sm text-slate-800">{item.name}</span>
                          </button>
                          <div className="text-right text-[11px] text-slate-500">
                            <div>{item.is_folder ? "Folder" : formatBytes(item.size)}</div>
                            <div>{item.last_modified_date_time || "-"}</div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                  {itemsError ? <p className="text-xs text-rose-700">{itemsError}</p> : null}
                </CardContent>
              </Card>

              <Card className="border-slate-200/70">
                <CardHeader className="border-b border-slate-200/70 bg-slate-50/70 py-3">
                  <CardTitle className="text-sm text-slate-900">Preview</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3 pt-3">
                  {!selectedFile ? (
                    <p className="text-xs text-slate-500">Select a file to preview.</p>
                  ) : (
                    <>
                      <div className="text-sm font-semibold text-slate-900">{selectedFile.name}</div>
                      <div className="flex flex-wrap gap-2">
                        {selectedFile.web_url ? (
                          <Button asChild size="sm" variant="outline">
                            <a href={selectedFile.web_url} target="_blank" rel="noopener noreferrer">
                              Open in SharePoint
                              <ExternalLink className="h-4 w-4" />
                            </a>
                          </Button>
                        ) : null}
                      </div>

                      {isLoadingPreview ? (
                        <p className="text-xs text-slate-500">Loading preview...</p>
                      ) : null}
                      {previewError ? <p className="text-xs text-rose-700">{previewError}</p> : null}

                      {previewKind === "pdf" && previewBlobUrl ? (
                        <iframe
                          src={previewBlobUrl}
                          title="SharePoint PDF Preview"
                          className="h-[32rem] w-full rounded-lg border border-slate-200"
                        />
                      ) : null}

                      {previewKind === "image" && previewBlobUrl ? (
                        <img
                          src={previewBlobUrl}
                          alt={selectedFile.name}
                          className="max-h-[32rem] w-full rounded-lg border border-slate-200 object-contain"
                        />
                      ) : null}

                      {previewKind === "external" ? (
                        <p className="text-xs text-slate-500">
                          In-app preview is currently available for PDF and image files only.
                        </p>
                      ) : null}
                    </>
                  )}
                </CardContent>
              </Card>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
