"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { usePathname } from "next/navigation";

import { ApiError, apiFetch } from "@/lib/api";

type TannerAssistantResponse = {
  reply: string;
};

type TannerTranscriptionResponse = {
  transcript: string;
};

type TannerChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
};

type TannerTab = "chat" | "charting";
type TannerNoteType = "SOAP" | "DAP";

const STORAGE_OPEN_KEY = "vehr_tanner_drawer_open";
const STORAGE_TAB_KEY = "vehr_tanner_active_tab";

const QUICK_ACTIONS = [
  { label: "Find policy", seed: "Find policy for " },
  { label: "Draft note", seed: "Draft SOAP note for " },
  { label: "Draft letter", seed: "Draft letter for " },
] as const;

function deriveContext(pathname: string | null): { path: string; module: string } {
  const safePath = pathname && pathname.startsWith("/") ? pathname : "/";
  const parts = safePath.split("/").filter(Boolean);
  return {
    path: safePath,
    module: parts[0] ?? "dashboard",
  };
}

function toErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError || error instanceof Error) {
    return error.message || fallback;
  }
  return fallback;
}

function formatRelativeDate(value: string): string {
  const stamp = new Date(value);
  if (Number.isNaN(stamp.getTime())) return "";
  return stamp.toLocaleTimeString();
}

function formatNoteOutput(note: Record<string, string>, noteType: TannerNoteType): string {
  if (noteType === "SOAP") {
    return [
      `S: ${note.S ?? ""}`,
      `O: ${note.O ?? ""}`,
      `A: ${note.A ?? ""}`,
      `P: ${note.P ?? ""}`,
    ].join("\n\n");
  }
  return [
    `D: ${note.D ?? ""}`,
    `A: ${note.A ?? ""}`,
    `P: ${note.P ?? ""}`,
  ].join("\n\n");
}

export default function CopilotDrawer() {
  const pathname = usePathname();
  const context = useMemo(() => deriveContext(pathname), [pathname]);

  const [isOpen, setIsOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<TannerTab>("chat");

  const [chatDraft, setChatDraft] = useState("");
  const [chatMessages, setChatMessages] = useState<TannerChatMessage[]>([]);
  const [chatError, setChatError] = useState<string | null>(null);
  const [isSending, setIsSending] = useState(false);

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [recordedBlob, setRecordedBlob] = useState<Blob | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [isGeneratingNote, setIsGeneratingNote] = useState(false);
  const [chartingError, setChartingError] = useState<string | null>(null);
  const [noteType, setNoteType] = useState<TannerNoteType>("SOAP");
  const [transcript, setTranscript] = useState("");
  const [noteDraft, setNoteDraft] = useState("");

  const chatHistoryRef = useRef<HTMLDivElement | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const recorderChunksRef = useRef<Blob[]>([]);

  const canRecord = useMemo(() => {
    if (typeof window === "undefined") return false;
    return typeof window.MediaRecorder !== "undefined" && !!navigator.mediaDevices?.getUserMedia;
  }, []);

  useEffect(() => {
    try {
      const rawOpen = window.localStorage.getItem(STORAGE_OPEN_KEY);
      if (rawOpen === "1") setIsOpen(true);
      const rawTab = window.localStorage.getItem(STORAGE_TAB_KEY);
      if (rawTab === "chat" || rawTab === "charting") {
        setActiveTab(rawTab);
      }
    } catch {
      // ignore storage failures
    }
  }, []);

  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_OPEN_KEY, isOpen ? "1" : "0");
    } catch {
      // ignore storage failures
    }
  }, [isOpen]);

  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_TAB_KEY, activeTab);
    } catch {
      // ignore storage failures
    }
  }, [activeTab]);

  useEffect(() => {
    if (!chatHistoryRef.current) return;
    chatHistoryRef.current.scrollTop = chatHistoryRef.current.scrollHeight;
  }, [chatMessages]);

  useEffect(() => {
    return () => {
      try {
        if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
          mediaRecorderRef.current.stop();
        }
      } catch {
        // ignore teardown recorder failures
      }
      if (mediaStreamRef.current) {
        mediaStreamRef.current.getTracks().forEach((track) => track.stop());
        mediaStreamRef.current = null;
      }
    };
  }, []);

  async function handleSendChat(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const message = chatDraft.trim();
    if (!message || isSending) return;

    setChatError(null);
    setIsSending(true);
    setChatDraft("");

    const optimisticUser: TannerChatMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      content: message,
      created_at: new Date().toISOString(),
    };
    setChatMessages((current) => [...current, optimisticUser]);

    try {
      const response = await apiFetch<TannerAssistantResponse>("/api/v1/tanner-ai/assistant", {
        method: "POST",
        body: JSON.stringify({
          message,
          context: `module=${context.module}; path=${context.path}`,
        }),
      });

      setChatMessages((current) => [
        ...current,
        {
          id: `assistant-${Date.now()}`,
          role: "assistant",
          content: response.reply,
          created_at: new Date().toISOString(),
        },
      ]);
    } catch (error) {
      setChatError(toErrorMessage(error, "Tanner AI request failed"));
    } finally {
      setIsSending(false);
    }
  }

  function useQuickAction(seed: string) {
    setChatDraft((current) => (current.trim() ? current : seed));
  }

  async function startRecording() {
    if (!canRecord || isRecording) return;
    setChartingError(null);

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaStreamRef.current = stream;
      recorderChunksRef.current = [];

      const recorder = new MediaRecorder(stream);
      recorder.ondataavailable = (event: BlobEvent) => {
        if (event.data.size > 0) {
          recorderChunksRef.current.push(event.data);
        }
      };
      recorder.onstop = () => {
        const blob = new Blob(recorderChunksRef.current, { type: "audio/webm" });
        setRecordedBlob(blob);
        if (mediaStreamRef.current) {
          mediaStreamRef.current.getTracks().forEach((track) => track.stop());
          mediaStreamRef.current = null;
        }
      };

      mediaRecorderRef.current = recorder;
      setSelectedFile(null);
      setRecordedBlob(null);
      recorder.start();
      setIsRecording(true);
    } catch (error) {
      setChartingError(toErrorMessage(error, "Unable to start recording"));
    }
  }

  function stopRecording() {
    if (!mediaRecorderRef.current || mediaRecorderRef.current.state === "inactive") {
      return;
    }
    setIsRecording(false);
    mediaRecorderRef.current.stop();
  }

  function buildAudioFormData(): FormData | null {
    const formData = new FormData();
    if (recordedBlob) {
      formData.append("file", recordedBlob, `visit-${Date.now()}.webm`);
      return formData;
    }
    if (selectedFile) {
      formData.append("file", selectedFile, selectedFile.name);
      return formData;
    }
    return null;
  }

  async function transcribeVisitAudio() {
    setChartingError(null);
    const formData = buildAudioFormData();
    if (!formData) {
      setChartingError("Upload or record visit audio first.");
      return;
    }

    setIsTranscribing(true);
    try {
      const response = await apiFetch<TannerTranscriptionResponse>("/api/v1/tanner-ai/transcribe", {
        method: "POST",
        body: formData,
      });
      setTranscript(response.transcript);
    } catch (error) {
      setChartingError(toErrorMessage(error, "Unable to transcribe visit audio"));
    } finally {
      setIsTranscribing(false);
    }
  }

  async function generateStructuredNote() {
    const cleanedTranscript = transcript.trim();
    if (!cleanedTranscript) {
      setChartingError("Transcript is required before note generation.");
      return;
    }

    setChartingError(null);
    setIsGeneratingNote(true);
    try {
      const response = await apiFetch<Record<string, string>>("/api/v1/tanner-ai/note", {
        method: "POST",
        body: JSON.stringify({
          transcript: cleanedTranscript,
          note_type: noteType,
        }),
      });
      setNoteDraft(formatNoteOutput(response, noteType));
    } catch (error) {
      setChartingError(toErrorMessage(error, "Unable to generate structured note"));
    } finally {
      setIsGeneratingNote(false);
    }
  }

  async function copyNoteToClipboard() {
    if (!noteDraft.trim()) return;
    try {
      await navigator.clipboard.writeText(noteDraft);
    } catch {
      // ignore clipboard failures
    }
  }

  const hasAudioReady = !!selectedFile || !!recordedBlob;

  return (
    <>
      <button
        type="button"
        onClick={() => setIsOpen((prev) => !prev)}
        aria-label={isOpen ? "Close Tanner AI" : "Open Tanner AI"}
        data-testid="copilot-trigger"
        className={`fixed bottom-6 right-6 z-[2147483000] inline-flex h-14 min-w-[56px] items-center justify-center gap-2 rounded-full bg-slate-900 px-4 text-white shadow-lg transition-all hover:scale-105 ${
          isOpen ? "pointer-events-none opacity-0" : "opacity-100"
        }`}
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className="h-6 w-6">
          <path d="M7 8h10" />
          <path d="M7 12h10" />
          <path d="M7 16h6" />
          <path d="M5 4h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2h-6l-4 3v-3H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z" />
        </svg>
        <span className="text-xs font-semibold">AI</span>
      </button>

      <aside
        className={`fixed right-4 top-4 z-[2147482999] flex h-[calc(100vh-2rem)] w-[min(96vw,900px)] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl transition-transform duration-300 ${
          isOpen ? "translate-x-0" : "translate-x-[110%]"
        }`}
        aria-hidden={!isOpen}
      >
        <header className="border-b border-slate-200 px-4 py-3">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Tanner AI</div>
              <div className="mt-1 text-sm text-slate-700">Chat + Visit Charting</div>
              <div className="text-xs text-slate-500">
                Context: {context.module} | {context.path}
              </div>
            </div>
            <button
              type="button"
              onClick={() => setIsOpen(false)}
              className="rounded-md border border-slate-200 px-2 py-1 text-xs text-slate-600 hover:bg-slate-50"
            >
              Close
            </button>
          </div>
          <div className="mt-3 flex items-center gap-2">
            <button
              type="button"
              onClick={() => setActiveTab("chat")}
              className={`rounded-full border px-3 py-1 text-xs font-semibold transition-colors ${
                activeTab === "chat"
                  ? "border-cyan-300 bg-cyan-50 text-cyan-700"
                  : "border-slate-200 bg-white text-slate-600 hover:border-slate-300"
              }`}
            >
              Tanner Chat
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("charting")}
              className={`rounded-full border px-3 py-1 text-xs font-semibold transition-colors ${
                activeTab === "charting"
                  ? "border-cyan-300 bg-cyan-50 text-cyan-700"
                  : "border-slate-200 bg-white text-slate-600 hover:border-slate-300"
              }`}
            >
              Tanner Charting
            </button>
          </div>
        </header>

        {activeTab === "chat" ? (
          <section className="flex min-h-0 flex-1 flex-col">
            <div className="border-b border-slate-200 px-4 py-3">
              <div className="flex flex-wrap gap-2">
                {QUICK_ACTIONS.map((action) => (
                  <button
                    key={action.label}
                    type="button"
                    onClick={() => useQuickAction(action.seed)}
                    className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs text-slate-600 transition-colors hover:border-slate-300"
                  >
                    {action.label}
                  </button>
                ))}
                <button
                  type="button"
                  onClick={() => setChatMessages([])}
                  className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs text-slate-600 transition-colors hover:border-slate-300"
                >
                  Clear chat
                </button>
              </div>
            </div>

            <div ref={chatHistoryRef} className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-4">
              {!chatMessages.length ? (
                <div className="text-xs text-slate-500">Ask Tanner AI anything related to staff workflow.</div>
              ) : null}
              {chatMessages.map((message) => (
                <div
                  key={message.id}
                  className={`max-w-[92%] rounded-xl px-3 py-2 text-sm ${
                    message.role === "assistant"
                      ? "mr-auto bg-slate-100 text-slate-800"
                      : "ml-auto bg-cyan-700 text-white"
                  }`}
                >
                  <div className="whitespace-pre-wrap break-words">{message.content}</div>
                  <div className="mt-1 text-[10px] opacity-70">{formatRelativeDate(message.created_at)}</div>
                </div>
              ))}
            </div>

            <footer className="border-t border-slate-200 p-4">
              {chatError ? (
                <div className="mb-2 rounded-md border border-rose-200 bg-rose-50 px-2 py-1 text-xs text-rose-700">
                  {chatError}
                </div>
              ) : null}
              <form onSubmit={handleSendChat} className="flex items-end gap-2">
                <textarea
                  value={chatDraft}
                  onChange={(event) => setChatDraft(event.target.value)}
                  placeholder="Ask Tanner AI..."
                  rows={2}
                  className="min-h-[72px] flex-1 resize-y rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-800 focus:border-slate-300 focus:outline-none focus:ring-2 focus:ring-slate-200"
                />
                <button
                  type="submit"
                  disabled={isSending || !chatDraft.trim()}
                  className="h-10 rounded-lg bg-slate-900 px-4 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {isSending ? "Sending..." : "Send"}
                </button>
              </form>
            </footer>
          </section>
        ) : (
          <section className="grid min-h-0 flex-1 gap-0 lg:grid-cols-[1fr_1fr]">
            <div className="min-h-0 overflow-y-auto border-r border-slate-200 px-4 py-4">
              {chartingError ? (
                <div className="mb-3 rounded-md border border-rose-200 bg-rose-50 px-2 py-1 text-xs text-rose-700">
                  {chartingError}
                </div>
              ) : null}

              <div className="space-y-2">
                <div className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Visit Audio</div>
                <input
                  type="file"
                  accept="audio/*"
                  onChange={(event) => {
                    const file = event.target.files?.[0] ?? null;
                    setSelectedFile(file);
                    setRecordedBlob(null);
                  }}
                  className="block w-full text-sm text-slate-700"
                />
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => void startRecording()}
                    disabled={!canRecord || isRecording}
                    className="rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-700 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {isRecording ? "Recording..." : "Start recording"}
                  </button>
                  <button
                    type="button"
                    onClick={stopRecording}
                    disabled={!isRecording}
                    className="rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-700 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    Stop recording
                  </button>
                </div>
                {!canRecord ? (
                  <div className="text-xs text-slate-500">Browser recording is unavailable on this device.</div>
                ) : null}
                <div className="text-xs text-slate-600">
                  Source: {recordedBlob ? "Recorded visit audio" : selectedFile ? selectedFile.name : "No audio selected"}
                </div>
              </div>

              <div className="mt-4 space-y-2">
                <div className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Transcription</div>
                <button
                  type="button"
                  onClick={() => void transcribeVisitAudio()}
                  disabled={!hasAudioReady || isTranscribing}
                  className="rounded-lg bg-slate-900 px-3 py-2 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {isTranscribing ? "Transcribing..." : "Transcribe visit"}
                </button>
                <textarea
                  value={transcript}
                  onChange={(event) => setTranscript(event.target.value)}
                  placeholder="Transcript appears here..."
                  className="min-h-[200px] w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-800"
                />
              </div>
            </div>

            <div className="min-h-0 overflow-y-auto px-4 py-4">
              <div className="space-y-2">
                <div className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Structured Note</div>
                <div className="flex items-center gap-2">
                  <select
                    value={noteType}
                    onChange={(event) => setNoteType(event.target.value as TannerNoteType)}
                    className="h-9 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-700"
                  >
                    <option value="SOAP">SOAP</option>
                    <option value="DAP">DAP</option>
                  </select>
                  <button
                    type="button"
                    onClick={() => void generateStructuredNote()}
                    disabled={isGeneratingNote || !transcript.trim()}
                    className="rounded-lg bg-slate-900 px-3 py-2 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {isGeneratingNote ? "Generating..." : `Generate ${noteType}`}
                  </button>
                  <button
                    type="button"
                    onClick={() => void copyNoteToClipboard()}
                    disabled={!noteDraft.trim()}
                    className="rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-700 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    Copy note
                  </button>
                </div>
                <textarea
                  value={noteDraft}
                  onChange={(event) => setNoteDraft(event.target.value)}
                  placeholder="Generated SOAP/DAP note appears here..."
                  className="min-h-[360px] w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-800"
                />
              </div>
            </div>
          </section>
        )}
      </aside>
    </>
  );
}
