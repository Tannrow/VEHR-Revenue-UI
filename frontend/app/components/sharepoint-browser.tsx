"use client";

import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  CheckCircle2,
  ExternalLink,
  FileText,
  Folder,
  Image as ImageIcon,
  Link2,
  RefreshCw,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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

type SharePointWorkspaceResponse = {
  site: SharePointSite;
  drives: SharePointDrive[];
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

type SharePointPreviewResponse = {
  id: string;
  name: string;
  web_url: string;
  mime_type?: string | null;
  preview_kind: "pdf" | "image" | "external";
  is_previewable: boolean;
  preview_url?: string | null;
  download_url?: string | null;
};

type FolderCrumb = {
  id: string;
  name: string;
};

type PreviewKind = "none" | "pdf" | "image" | "office" | "external";

type SharePointBrowserProps = {
  eyebrow?: string;
  title: string;
  subtitle: string;
};

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

function toErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return fallback;
}

export default function SharePointBrowser({
  eyebrow = "SharePoint",
  title,
  subtitle,
}: SharePointBrowserProps) {
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

  const [isLoadingWorkspace, setIsLoadingWorkspace] = useState(false);
  const [workspaceError, setWorkspaceError] = useState<string | null>(null);
  const [workspace, setWorkspace] = useState<SharePointWorkspaceResponse | null>(null);

  const [isLoadingItems, setIsLoadingItems] = useState(false);
  const [itemsError, setItemsError] = useState<string | null>(null);
  const [items, setItems] = useState<SharePointItem[]>([]);
  const [selectedDrive, setSelectedDrive] = useState<SharePointDrive | null>(null);
  const [folderStack, setFolderStack] = useState<FolderCrumb[]>([]);

  const [selectedFile, setSelectedFile] = useState<SharePointItem | null>(null);
  const [previewKind, setPreviewKind] = useState<PreviewKind>("none");
  const [isLoadingPreview, setIsLoadingPreview] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [previewBlobUrl, setPreviewBlobUrl] = useState<string | null>(null);
  const [previewFrameUrl, setPreviewFrameUrl] = useState<string | null>(null);

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
      setConnectError(toErrorMessage(error, "Unable to start Microsoft connection."));
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
      } else {
        setConnectionState("error");
      }
      setConnectionMessage(toErrorMessage(error, "Unable to test Microsoft connection."));
    } finally {
      setIsTestingConnection(false);
    }
  }

  function clearPreview() {
    setSelectedFile(null);
    setPreviewKind("none");
    setPreviewError(null);
    setPreviewFrameUrl(null);
    if (previewBlobUrl) {
      URL.revokeObjectURL(previewBlobUrl);
      setPreviewBlobUrl(null);
    }
  }

  async function loadDriveItems(nextDrive: SharePointDrive, parentId: string, crumbs: FolderCrumb[]) {
    setItemsError(null);
    setIsLoadingItems(true);
    clearPreview();

    try {
      const response = await apiFetch<SharePointItem[]>(
        `/api/v1/integrations/microsoft/sharepoint/drives/${encodeURIComponent(nextDrive.id)}/items?parentId=${encodeURIComponent(parentId)}`,
        { cache: "no-store" },
      );
      setSelectedDrive(nextDrive);
      setFolderStack(crumbs);
      setItems(response);
    } catch (error) {
      setItems([]);
      setItemsError(toErrorMessage(error, "Unable to load drive items."));
    } finally {
      setIsLoadingItems(false);
    }
  }

  async function loadWorkspace() {
    setIsLoadingWorkspace(true);
    setWorkspaceError(null);
    setWorkspace(null);
    setItems([]);
    setSelectedDrive(null);
    setFolderStack([]);
    clearPreview();

    try {
      const response = await apiFetch<SharePointWorkspaceResponse>(
        "/api/v1/integrations/microsoft/sharepoint/workspace",
        { cache: "no-store" },
      );
      setWorkspace(response);

      const firstDrive = response.drives[0];
      if (firstDrive) {
        await loadDriveItems(firstDrive, "root", []);
      }
    } catch (error) {
      setWorkspaceError(toErrorMessage(error, "Unable to load SharePoint workspace."));
    } finally {
      setIsLoadingWorkspace(false);
    }
  }

  useEffect(() => {
    void testConnection();
    void loadWorkspace();
  }, []);

  async function openFilePreview(item: SharePointItem) {
    if (!selectedDrive) {
      setPreviewError("Select a drive first.");
      return;
    }

    clearPreview();
    setSelectedFile(item);
    setIsLoadingPreview(true);

    try {
      const preview = await apiFetch<SharePointPreviewResponse>(
        `/api/v1/integrations/microsoft/sharepoint/items/${encodeURIComponent(item.id)}/preview?driveId=${encodeURIComponent(selectedDrive.id)}`,
        { cache: "no-store" },
      );

      setSelectedFile({
        ...item,
        web_url: preview.web_url || item.web_url,
        mime_type: preview.mime_type ?? item.mime_type,
      });

      if (preview.is_previewable && preview.download_url) {
        const blob = await apiFetchBlob(preview.download_url, { cache: "no-store" });
        const objectUrl = URL.createObjectURL(blob);
        setPreviewBlobUrl(objectUrl);
        setPreviewKind(preview.preview_kind === "image" ? "image" : "pdf");
        return;
      }

      if (preview.preview_url) {
        setPreviewFrameUrl(preview.preview_url);
        setPreviewKind("office");
        return;
      }

      setPreviewKind("external");
    } catch (error) {
      setPreviewKind("external");
      setPreviewError(toErrorMessage(error, "Unable to load preview for this file."));
    } finally {
      setIsLoadingPreview(false);
    }
  }

  const breadcrumbLabel = useMemo(() => {
    if (folderStack.length === 0) {
      return "Root";
    }
    return folderStack.map((crumb) => crumb.name).join(" / ");
  }, [folderStack]);

  return (
    <div className="flex flex-col gap-6">
      <div className="space-y-2">
        <p className="text-[11px] font-semibold uppercase tracking-[0.32em] text-slate-400">
          {eyebrow}
        </p>
        <h1 className="text-3xl font-semibold tracking-tight text-slate-900">{title}</h1>
        <p className="text-sm text-slate-500">{subtitle}</p>
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
          <CardTitle className="text-base text-slate-900">Workspace</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 pt-5">
          <div className="rounded-xl border border-slate-200 bg-white p-4">
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Pinned Workspace</p>
            <h2 className="mt-1 text-lg font-semibold text-slate-900">
              {workspace?.site.name || "Valley Health Home Page"}
            </h2>
            <p className="mt-1 text-sm text-slate-600">
              Browse your organization SharePoint documents through Microsoft Graph.
            </p>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              {workspace?.site.web_url ? (
                <Button asChild size="sm" variant="outline">
                  <a href={workspace.site.web_url} target="_blank" rel="noopener noreferrer">
                    Open in SharePoint
                    <ExternalLink className="h-4 w-4" />
                  </a>
                </Button>
              ) : null}
              <Button type="button" size="sm" variant="outline" onClick={() => void loadWorkspace()}>
                <RefreshCw className="h-4 w-4" />
                Reload Workspace
              </Button>
            </div>
          </div>

          <div className="grid gap-3 md:grid-cols-2">
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

            <div className="flex flex-wrap items-center gap-3 rounded-lg border border-slate-200 bg-slate-50 p-3">
              <Button type="button" onClick={handleConnectMicrosoft} disabled={isConnecting}>
                {isConnecting ? "Redirecting..." : "Connect Microsoft"}
                <ExternalLink className="h-4 w-4" />
              </Button>
              <Button type="button" variant="outline" onClick={testConnection} disabled={isTestingConnection}>
                {isTestingConnection ? "Testing..." : "Test Connection"}
              </Button>
            </div>
          </div>

          {connectError ? <p className="text-sm text-rose-700">{connectError}</p> : null}
          {workspaceError ? <p className="text-sm text-rose-700">{workspaceError}</p> : null}

          <div className="flex items-start gap-2 rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs text-slate-600">
            <Link2 className="mt-0.5 h-4 w-4 shrink-0 text-slate-500" />
            <span>
              Embedded SharePoint iframes are blocked by policy; this workspace uses Microsoft Graph APIs only.
            </span>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 xl:grid-cols-[280px_1fr_1fr]">
        <Card className="border-slate-200/70 shadow-sm">
          <CardHeader className="border-b border-slate-200/70 bg-slate-50/70 py-3">
            <CardTitle className="text-sm text-slate-900">Document Libraries</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 pt-3">
            {isLoadingWorkspace ? (
              <p className="text-xs text-slate-500">Loading workspace...</p>
            ) : (workspace?.drives.length ?? 0) === 0 ? (
              <p className="text-xs text-slate-500">No document libraries found for this workspace.</p>
            ) : (
              workspace?.drives.map((drive) => (
                <button
                  key={drive.id}
                  type="button"
                  onClick={() => void loadDriveItems(drive, "root", [])}
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
          </CardContent>
        </Card>

        <Card className="border-slate-200/70 shadow-sm">
          <CardHeader className="border-b border-slate-200/70 bg-slate-50/70 py-3">
            <CardTitle className="text-sm text-slate-900">Explorer</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 pt-3">
            <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={!selectedDrive || folderStack.length === 0}
                onClick={() => {
                  const next = folderStack.slice(0, -1);
                  const parentId = next.length === 0 ? "root" : next[next.length - 1].id;
                  if (selectedDrive) {
                    void loadDriveItems(selectedDrive, parentId, next);
                  }
                }}
              >
                Back
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={!selectedDrive}
                onClick={() => {
                  if (selectedDrive) {
                    void loadDriveItems(selectedDrive, "root", []);
                  }
                }}
              >
                Root
              </Button>
              <span className="truncate">{breadcrumbLabel}</span>
            </div>

            {isLoadingItems ? (
              <p className="text-xs text-slate-500">Loading items...</p>
            ) : items.length === 0 ? (
              <p className="text-xs text-slate-500">Select a document library to browse files and folders.</p>
            ) : (
              <div className="space-y-2">
                {items.map((item) => (
                  <div
                    key={item.id}
                    className={`flex items-center justify-between gap-3 rounded-lg border px-3 py-2 ${
                      selectedFile?.id === item.id ? "border-cyan-300 bg-cyan-50" : "border-slate-200 bg-white"
                    }`}
                  >
                    <button
                      type="button"
                      onClick={() => {
                        if (item.is_folder) {
                          if (!selectedDrive) return;
                          void loadDriveItems(selectedDrive, item.id, [...folderStack, { id: item.id, name: item.name }]);
                          return;
                        }
                        void openFilePreview(item);
                      }}
                      className="flex min-w-0 flex-1 items-center gap-2 text-left"
                    >
                      {item.is_folder ? (
                        <Folder className="h-4 w-4 shrink-0 text-amber-600" />
                      ) : (item.mime_type || "").toLowerCase().startsWith("image/") ? (
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

        <Card className="border-slate-200/70 shadow-sm">
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

                {isLoadingPreview ? <p className="text-xs text-slate-500">Loading preview...</p> : null}
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

                {previewKind === "office" && previewFrameUrl ? (
                  <div className="space-y-2">
                    <iframe
                      src={previewFrameUrl}
                      title="SharePoint Office Preview"
                      className="h-[32rem] w-full rounded-lg border border-slate-200"
                    />
                    <p className="text-xs text-slate-500">
                      If preview is blocked by policy, use Open in SharePoint.
                    </p>
                  </div>
                ) : null}

                {previewKind === "external" ? (
                  <p className="text-xs text-slate-500">
                    In-app preview is available for PDF and image files. Use Open in SharePoint for Office documents.
                  </p>
                ) : null}
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
