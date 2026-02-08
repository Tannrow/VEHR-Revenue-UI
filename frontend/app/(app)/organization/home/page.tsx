"use client";

import type { ComponentType, DragEvent } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  BadgeCheck,
  Beaker,
  BookOpen,
  Briefcase,
  Download,
  File,
  FileSignature,
  FileText,
  Folder,
  GraduationCap,
  Image as ImageIcon,
  Layers,
  PhoneCall,
  ShieldCheck,
  Upload,
  Users,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
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

type OrganizationNode = {
  id: string;
  tile_id: string;
  parent_id?: string | null;
  node_type: "folder" | "file";
  name: string;
  content?: string | null;
  storage_key?: string | null;
  media_type?: string | null;
  size_bytes?: number | null;
  sort_order: number;
  created_at: string;
  updated_at: string;
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

type PresignUploadResponse = {
  key: string;
  url: string;
  method: string;
  headers: Record<string, string>;
};

type PresignDownloadResponse = {
  url: string;
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

function formatBytes(size?: number | null): string {
  if (size == null) return "";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function guessContentType(file: File): string {
  if (file.type) return file.type;
  return "application/octet-stream";
}

export default function OrganizationHomePage() {
  const [tiles, setTiles] = useState<OrganizationTile[]>([]);
  const [announcements, setAnnouncements] = useState<Announcement[]>([]);
  const [workSummary, setWorkSummary] = useState<WorkSummary | null>(null);
  const [selectedTileId, setSelectedTileId] = useState<string | null>(null);
  const [folderPath, setFolderPath] = useState<Array<{ id: string; name: string }>>([]);
  const [nodes, setNodes] = useState<OrganizationNode[]>([]);
  const [selectedFile, setSelectedFile] = useState<OrganizationNode | null>(null);
  const [fileDraftName, setFileDraftName] = useState("");
  const [fileDraftContent, setFileDraftContent] = useState("");
  const [newFolderName, setNewFolderName] = useState("");
  const [newFileName, setNewFileName] = useState("");
  const [loading, setLoading] = useState(true);
  const [workspaceLoading, setWorkspaceLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [workspaceError, setWorkspaceError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const currentParentId = folderPath.length > 0 ? folderPath[folderPath.length - 1].id : null;

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
        if (home.tiles.length > 0) {
          setSelectedTileId((current) => current ?? home.tiles[0].id);
        }
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

  const selectedTile = useMemo(
    () => tiles.find((tile) => tile.id === selectedTileId) ?? null,
    [tiles, selectedTileId],
  );

  async function loadNodes(tileId: string, parentId: string | null) {
    const params = parentId ? `?parent_id=${encodeURIComponent(parentId)}` : "";
    const data = await apiFetch<OrganizationNode[]>(`/api/v1/organization/tiles/${tileId}/nodes${params}`, {
      cache: "no-store",
    });
    setNodes(data);
  }

  useEffect(() => {
    if (!selectedTileId) {
      setNodes([]);
      setSelectedFile(null);
      return;
    }
    const tileId = selectedTileId;

    let mounted = true;
    async function loadWorkspace() {
      try {
        setWorkspaceLoading(true);
        setWorkspaceError(null);
        await loadNodes(tileId, currentParentId);
        if (!mounted) return;
      } catch (loadError) {
        if (!mounted) return;
        setWorkspaceError(toErrorMessage(loadError, "Failed to load workspace items"));
      } finally {
        if (mounted) setWorkspaceLoading(false);
      }
    }

    loadWorkspace();
    return () => {
      mounted = false;
    };
  }, [selectedTileId, currentParentId]);

  function selectTile(tileId: string) {
    setSelectedTileId(tileId);
    setFolderPath([]);
    setSelectedFile(null);
    setWorkspaceError(null);
  }

  function openFolder(node: OrganizationNode) {
    setFolderPath((current) => [...current, { id: node.id, name: node.name }]);
    setSelectedFile(null);
  }

  function openFile(node: OrganizationNode) {
    setSelectedFile(node);
    setFileDraftName(node.name);
    setFileDraftContent(node.content ?? "");
  }

  function goToRoot() {
    setFolderPath([]);
    setSelectedFile(null);
  }

  function goToPathIndex(index: number) {
    setFolderPath((current) => current.slice(0, index + 1));
    setSelectedFile(null);
  }

  async function createNode(nodeType: "folder" | "file") {
    if (!selectedTileId) return;
    const name = (nodeType === "folder" ? newFolderName : newFileName).trim();
    if (!name) return;

    try {
      setWorkspaceError(null);
      await apiFetch<OrganizationNode>(`/api/v1/organization/tiles/${selectedTileId}/nodes`, {
        method: "POST",
        body: JSON.stringify({
          node_type: nodeType,
          name,
          parent_id: currentParentId,
          content: nodeType === "file" ? "" : null,
        }),
      });
      if (nodeType === "folder") setNewFolderName("");
      if (nodeType === "file") setNewFileName("");
      await loadNodes(selectedTileId, currentParentId);
    } catch (createError) {
      setWorkspaceError(toErrorMessage(createError, `Failed to create ${nodeType}`));
    }
  }

  async function saveFile() {
    if (!selectedFile) return;
    try {
      setWorkspaceError(null);
      const patchPayload: Record<string, unknown> = { name: fileDraftName };
      if (!selectedFile.storage_key) {
        patchPayload.content = fileDraftContent;
      }
      const updated = await apiFetch<OrganizationNode>(`/api/v1/organization/nodes/${selectedFile.id}`, {
        method: "PATCH",
        body: JSON.stringify(patchPayload),
      });
      setSelectedFile(updated);
      if (selectedTileId) {
        await loadNodes(selectedTileId, currentParentId);
      }
    } catch (saveError) {
      setWorkspaceError(toErrorMessage(saveError, "Failed to save file"));
    }
  }

  async function uploadFiles(files: FileList | File[]) {
    if (!selectedTileId) return;
    const list = Array.from(files);
    if (list.length === 0) return;

    try {
      setWorkspaceError(null);
      setUploading(true);
      for (const file of list) {
        const contentType = guessContentType(file);
        const presign = await apiFetch<PresignUploadResponse>("/api/v1/uploads/presign", {
          method: "POST",
          body: JSON.stringify({ filename: file.name, content_type: contentType }),
        });

        const uploadResponse = await fetch(presign.url, {
          method: presign.method,
          headers: presign.headers,
          body: file,
        });
        if (!uploadResponse.ok) {
          throw new Error(`Upload failed for ${file.name}`);
        }

        await apiFetch<OrganizationNode>(`/api/v1/organization/tiles/${selectedTileId}/nodes`, {
          method: "POST",
          body: JSON.stringify({
            node_type: "file",
            name: file.name,
            parent_id: currentParentId,
            storage_key: presign.key,
            media_type: contentType,
            size_bytes: file.size,
          }),
        });
      }
      await loadNodes(selectedTileId, currentParentId);
    } catch (uploadError) {
      setWorkspaceError(toErrorMessage(uploadError, "Failed to upload one or more files"));
    } finally {
      setUploading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragActive(false);
    void uploadFiles(event.dataTransfer.files);
  }

  function onDragOver(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragActive(true);
  }

  function onDragLeave(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragActive(false);
  }

  async function downloadSelectedFile() {
    if (!selectedFile?.storage_key) return;
    try {
      setWorkspaceError(null);
      const response = await apiFetch<PresignDownloadResponse>(
        `/api/v1/uploads/${selectedFile.storage_key}/download`,
      );
      window.open(response.url, "_blank", "noopener,noreferrer");
    } catch (downloadError) {
      setWorkspaceError(toErrorMessage(downloadError, "Failed to prepare file download"));
    }
  }

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
                const isSelected = tile.id === selectedTileId;
                return (
                  <button
                    key={tile.id}
                    type="button"
                    onClick={() => selectTile(tile.id)}
                    className={`rounded-lg border p-4 text-left transition ${
                      isSelected
                        ? "border-slate-900 bg-slate-900 text-white"
                        : "border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50"
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <span className={`flex h-10 w-10 items-center justify-center rounded-lg ${isSelected ? "bg-slate-700 text-white" : "bg-slate-100 text-slate-700"}`}>
                        <Icon className="h-5 w-5" />
                      </span>
                      <div>
                        <div className={`text-sm font-semibold ${isSelected ? "text-white" : "text-slate-900"}`}>{tile.title}</div>
                        <div className={`text-xs ${isSelected ? "text-slate-300" : "text-slate-500"}`}>Workspace folder</div>
                      </div>
                    </div>
                  </button>
                );
              })}
            </CardContent>
          </Card>
        ))}
      </div>

      <Card className="border-slate-200/70 shadow-sm">
        <CardHeader className="border-b border-slate-200/70 bg-slate-50/70">
          <CardTitle className="text-base">
            {selectedTile ? `${selectedTile.title} Workspace` : "Workspace"}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 pt-5">
          <div className="flex flex-wrap items-center gap-2 text-sm text-slate-600">
            <button type="button" onClick={goToRoot} className="rounded border border-slate-200 bg-white px-2 py-1 hover:bg-slate-50">
              Root
            </button>
            {folderPath.map((segment, index) => (
              <div key={segment.id} className="flex items-center gap-2">
                <span>/</span>
                <button
                  type="button"
                  onClick={() => goToPathIndex(index)}
                  className="rounded border border-slate-200 bg-white px-2 py-1 hover:bg-slate-50"
                >
                  {segment.name}
                </button>
              </div>
            ))}
          </div>

          {workspaceError ? (
            <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{workspaceError}</div>
          ) : null}

          <div className="grid gap-3 lg:grid-cols-3">
            <div className="flex gap-2">
              <Input
                placeholder={currentParentId ? "Create subfolder" : "Add core folder"}
                value={newFolderName}
                onChange={(event) => setNewFolderName(event.target.value)}
              />
              <Button type="button" onClick={() => createNode("folder")} disabled={!selectedTileId}>
                Add
              </Button>
            </div>
            <div className="flex gap-2">
              <Input
                placeholder="Create note file"
                value={newFileName}
                onChange={(event) => setNewFileName(event.target.value)}
              />
              <Button type="button" onClick={() => createNode("file")} disabled={!selectedTileId}>
                Add
              </Button>
            </div>
            <div className="flex items-center justify-start lg:justify-end">
              <input
                ref={fileInputRef}
                type="file"
                className="hidden"
                multiple
                onChange={(event) => {
                  if (event.target.files) {
                    void uploadFiles(event.target.files);
                  }
                }}
              />
              <Button
                type="button"
                variant="outline"
                disabled={!selectedTileId || uploading}
                onClick={() => fileInputRef.current?.click()}
              >
                <Upload className="mr-2 h-4 w-4" />
                {uploading ? "Uploading..." : "Upload File/Image"}
              </Button>
            </div>
          </div>

          <div
            onDrop={onDrop}
            onDragOver={onDragOver}
            onDragLeave={onDragLeave}
            className={`rounded-lg border-2 border-dashed p-4 text-sm transition ${
              dragActive
                ? "border-slate-500 bg-slate-100 text-slate-800"
                : "border-slate-200 bg-slate-50 text-slate-600"
            }`}
          >
            Drag and drop files here to upload into this folder.
          </div>

          <div className="rounded-lg border border-slate-200 bg-white">
            <div className="border-b border-slate-200 px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">
              Folder Items
            </div>
            <div className="p-3">
              {workspaceLoading ? <div className="text-sm text-slate-600">Loading workspace...</div> : null}
              {!workspaceLoading && nodes.length === 0 ? (
                <div className="text-sm text-slate-600">No files or folders yet.</div>
              ) : null}
              <div className="space-y-2">
                {nodes.map((node) => (
                  <button
                    key={node.id}
                    type="button"
                    onClick={() => (node.node_type === "folder" ? openFolder(node) : openFile(node))}
                    className="flex w-full items-center justify-between rounded border border-slate-200 bg-slate-50 px-3 py-2 text-left hover:bg-slate-100"
                  >
                    <div className="flex items-center gap-2 text-sm text-slate-800">
                      {node.node_type === "folder" ? (
                        <Folder className="h-4 w-4" />
                      ) : node.media_type?.startsWith("image/") ? (
                        <ImageIcon className="h-4 w-4" />
                      ) : (
                        <File className="h-4 w-4" />
                      )}
                      <span>{node.name}</span>
                    </div>
                    <span className="text-xs text-slate-500">
                      {node.node_type === "folder" ? "Open" : node.storage_key ? `Uploaded ${formatBytes(node.size_bytes)}` : "Edit"}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          </div>

          {selectedFile ? (
            <div className="space-y-3 rounded-lg border border-slate-200 bg-white p-4">
              <div className="text-sm font-semibold text-slate-900">{selectedFile.storage_key ? "File Details" : "Edit File"}</div>
              <Input
                value={fileDraftName}
                onChange={(event) => setFileDraftName(event.target.value)}
                placeholder="File name"
              />

              {selectedFile.storage_key ? (
                <div className="space-y-2 text-sm text-slate-600">
                  <div>Storage key: {selectedFile.storage_key}</div>
                  <div>Media type: {selectedFile.media_type || "unknown"}</div>
                  <div>Size: {formatBytes(selectedFile.size_bytes) || "unknown"}</div>
                  <div className="flex gap-2">
                    <Button type="button" onClick={saveFile}>
                      Save Name
                    </Button>
                    <Button type="button" variant="outline" onClick={downloadSelectedFile}>
                      <Download className="mr-2 h-4 w-4" />
                      Download
                    </Button>
                  </div>
                </div>
              ) : (
                <>
                  <textarea
                    value={fileDraftContent}
                    onChange={(event) => setFileDraftContent(event.target.value)}
                    placeholder="File contents"
                    className="min-h-[180px] w-full rounded-md border border-slate-200 px-3 py-2 text-sm"
                  />
                  <div className="flex justify-end">
                    <Button type="button" onClick={saveFile}>
                      Save File
                    </Button>
                  </div>
                </>
              )}
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
