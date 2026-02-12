"use client";

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { usePathname } from "next/navigation";

import { ApiError, apiFetch } from "@/lib/api";

type AiThreadSummary = {
  id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
  last_message_at: string | null;
  last_message_preview: string | null;
};

type AiMessage = {
  id: string;
  thread_id: string;
  role: "user" | "assistant" | "tool";
  content: string;
  created_at: string;
};

type AiChatResponse = {
  thread: AiThreadSummary;
  assistant_message: AiMessage;
  tool_results: Record<string, unknown>;
  fallback: boolean;
};

type AiContextPayload = {
  path: string;
  module: string;
  entity_type?: string;
  entity_id?: string;
  quick_action?: string;
};

const STORAGE_OPEN_KEY = "vehr_copilot_drawer_open";
const STORAGE_THREAD_KEY = "vehr_copilot_thread_id";

const QUICK_ACTIONS = [
  { label: "Find policy", value: "find_policy", seed: "Find policy for " },
  { label: "Draft note", value: "draft_note", seed: "Draft SOAP note for " },
  { label: "Draft letter", value: "draft_letter", seed: "Draft letter for " },
] as const;

function deriveContext(pathname: string | null): AiContextPayload {
  const safePath = pathname && pathname.startsWith("/") ? pathname : "/";
  const parts = safePath.split("/").filter(Boolean);
  const moduleName = parts[0] ?? "dashboard";
  const idLike = parts.find((item) => /^[a-z0-9-]{8,}$/i.test(item));

  return {
    path: safePath,
    module: moduleName,
    entity_type: parts.length >= 2 ? moduleName : undefined,
    entity_id: idLike,
  };
}

function formatRelativeDate(value: string | null): string {
  if (!value) return "";
  const stamp = new Date(value);
  if (Number.isNaN(stamp.getTime())) return "";
  return stamp.toLocaleString();
}

function messageBubbleClass(role: AiMessage["role"]): string {
  if (role === "assistant") {
    return "mr-auto bg-slate-100 text-slate-800";
  }
  if (role === "tool") {
    return "mr-auto bg-amber-100 text-amber-900";
  }
  return "ml-auto bg-cyan-700 text-white";
}

export default function CopilotDrawer() {
  const pathname = usePathname();

  const [isOpen, setIsOpen] = useState(false);
  const [threads, setThreads] = useState<AiThreadSummary[]>([]);
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null);
  const [messages, setMessages] = useState<AiMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [pendingQuickAction, setPendingQuickAction] = useState<string | null>(null);
  const [isLoadingThreads, setIsLoadingThreads] = useState(false);
  const [isLoadingMessages, setIsLoadingMessages] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const context = useMemo(() => deriveContext(pathname), [pathname]);
  const historyRef = useRef<HTMLDivElement | null>(null);
  const streamTimersRef = useRef<number[]>([]);

  const clearStreamingTimers = useCallback(() => {
    for (const id of streamTimersRef.current) {
      window.clearInterval(id);
    }
    streamTimersRef.current = [];
  }, []);

  useEffect(() => {
    try {
      const rawOpen = window.localStorage.getItem(STORAGE_OPEN_KEY);
      if (rawOpen === "1") {
        setIsOpen(true);
      }
      const rawThread = window.localStorage.getItem(STORAGE_THREAD_KEY);
      if (rawThread) {
        setActiveThreadId(rawThread);
      }
    } catch {
      // Ignore localStorage access errors.
    }
  }, []);

  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_OPEN_KEY, isOpen ? "1" : "0");
    } catch {
      // Ignore localStorage access errors.
    }
  }, [isOpen]);

  useEffect(() => {
    try {
      if (activeThreadId) {
        window.localStorage.setItem(STORAGE_THREAD_KEY, activeThreadId);
      } else {
        window.localStorage.removeItem(STORAGE_THREAD_KEY);
      }
    } catch {
      // Ignore localStorage access errors.
    }
  }, [activeThreadId]);

  useEffect(() => {
    if (!historyRef.current) return;
    historyRef.current.scrollTop = historyRef.current.scrollHeight;
  }, [messages]);

  useEffect(() => {
    return () => {
      clearStreamingTimers();
    };
  }, [clearStreamingTimers]);

  const loadThreads = useCallback(
    async (preferredThreadId?: string) => {
      if (!isOpen) return;
      setIsLoadingThreads(true);
      try {
        const rows = await apiFetch<AiThreadSummary[]>("/api/v1/ai/threads", { cache: "no-store" });
        setThreads(rows);

        if (preferredThreadId) {
          setActiveThreadId(preferredThreadId);
          return;
        }

        if (!rows.length) {
          setActiveThreadId(null);
          setMessages([]);
          return;
        }

        setActiveThreadId((prev) => {
          if (prev && rows.some((item) => item.id === prev)) {
            return prev;
          }
          return rows[0]?.id ?? null;
        });
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : "Failed to load threads");
      } finally {
        setIsLoadingThreads(false);
      }
    },
    [isOpen]
  );

  const loadMessages = useCallback(
    async (threadId: string) => {
      setIsLoadingMessages(true);
      setError(null);
      try {
        const rows = await apiFetch<AiMessage[]>(`/api/v1/ai/threads/${encodeURIComponent(threadId)}/messages`, {
          cache: "no-store",
        });
        setMessages(rows);
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : "Failed to load messages");
      } finally {
        setIsLoadingMessages(false);
      }
    },
    []
  );

  useEffect(() => {
    if (!isOpen) return;
    void loadThreads();
  }, [isOpen, loadThreads]);

  useEffect(() => {
    if (!isOpen || !activeThreadId) return;
    void loadMessages(activeThreadId);
  }, [activeThreadId, isOpen, loadMessages]);

  function runAssistantStreaming(message: AiMessage): Promise<void> {
    clearStreamingTimers();

    const streamMessageId = `stream-${message.id}`;
    const fullText = message.content || "";

    setMessages((prev) => [
      ...prev,
      {
        ...message,
        id: streamMessageId,
        content: "",
      },
    ]);

    if (!fullText) {
      return Promise.resolve();
    }

    const chunkSize = Math.max(1, Math.ceil(fullText.length / 80));

    return new Promise((resolve) => {
      let cursor = 0;
      const timer = window.setInterval(() => {
        cursor = Math.min(fullText.length, cursor + chunkSize);
        const nextContent = fullText.slice(0, cursor);
        setMessages((prev) =>
          prev.map((entry) =>
            entry.id === streamMessageId
              ? {
                  ...entry,
                  content: nextContent,
                }
              : entry
          )
        );

        if (cursor >= fullText.length) {
          window.clearInterval(timer);
          streamTimersRef.current = streamTimersRef.current.filter((id) => id !== timer);
          setMessages((prev) => prev.map((entry) => (entry.id === streamMessageId ? message : entry)));
          resolve();
        }
      }, 18);

      streamTimersRef.current.push(timer);
    });
  }

  async function handleSend(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const content = draft.trim();
    if (!content || isSending) return;

    const optimisticMessageId = `optimistic-user-${Date.now()}`;
    const optimisticThreadId = activeThreadId ?? "pending-thread";

    setIsSending(true);
    setError(null);
    setDraft("");

    setMessages((prev) => [
      ...prev,
      {
        id: optimisticMessageId,
        thread_id: optimisticThreadId,
        role: "user",
        content,
        created_at: new Date().toISOString(),
      },
    ]);

    const quickAction = pendingQuickAction || undefined;
    setPendingQuickAction(null);

    try {
      const response = await apiFetch<AiChatResponse>("/api/v1/ai/chat", {
        method: "POST",
        body: JSON.stringify({
          thread_id: activeThreadId,
          message: content,
          context: {
            ...context,
            quick_action: quickAction,
          },
        }),
      });

      const nextThreadId = response.thread.id;
      setActiveThreadId(nextThreadId);
      setMessages((prev) =>
        prev.map((entry) =>
          entry.id === optimisticMessageId
            ? {
                ...entry,
                thread_id: nextThreadId,
              }
            : entry
        )
      );

      await loadThreads(nextThreadId);
      await runAssistantStreaming(response.assistant_message);
      await loadMessages(nextThreadId);
    } catch (sendError) {
      const details = sendError instanceof ApiError ? sendError.message : sendError instanceof Error ? sendError.message : "Failed to send message";
      setError(details);
    } finally {
      setIsSending(false);
    }
  }

  function handleQuickAction(value: string, seed: string) {
    setPendingQuickAction(value);
    setDraft((prev) => (prev.trim() ? prev : seed));
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setIsOpen((prev) => !prev)}
        aria-label={isOpen ? "Close Tanner" : "Open Tanner"}
        data-testid="copilot-trigger"
        className="fixed bottom-6 right-6 z-[2147483000] inline-flex h-14 min-w-[56px] items-center justify-center gap-1 rounded-full bg-slate-900 px-3 text-white shadow-lg transition-transform hover:scale-105"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className="h-6 w-6">
          <path d="M7 8h10" />
          <path d="M7 12h10" />
          <path d="M7 16h6" />
          <path d="M5 4h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2h-6l-4 3v-3H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z" />
        </svg>
        <span className="text-xs font-semibold">T</span>
      </button>

      <aside
        className={`fixed right-4 top-4 z-[2147482999] flex h-[calc(100vh-2rem)] w-[min(96vw,860px)] overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl transition-transform duration-300 ${
          isOpen ? "translate-x-0" : "translate-x-[110%]"
        }`}
        aria-hidden={!isOpen}
      >
        <section className="flex w-[280px] flex-col border-r border-slate-200 bg-slate-50">
          <div className="border-b border-slate-200 px-4 py-3">
            <div className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Tanner</div>
            <div className="mt-1 text-sm text-slate-700">Support Threads</div>
          </div>
          <div className="flex-1 overflow-y-auto p-2">
            {isLoadingThreads ? <div className="px-2 py-4 text-xs text-slate-500">Loading threads...</div> : null}
            {!isLoadingThreads && threads.length === 0 ? <div className="px-2 py-4 text-xs text-slate-500">No threads yet.</div> : null}
            <div className="space-y-1">
              {threads.map((thread) => {
                const isActive = thread.id === activeThreadId;
                return (
                  <button
                    key={thread.id}
                    type="button"
                    onClick={() => setActiveThreadId(thread.id)}
                    className={`w-full rounded-lg border px-3 py-2 text-left transition-colors ${
                      isActive ? "border-cyan-300 bg-cyan-50" : "border-transparent bg-white hover:border-slate-200"
                    }`}
                  >
                    <div className="truncate text-sm font-medium text-slate-900">{thread.title || "Staff Support"}</div>
                    <div className="truncate text-xs text-slate-500">{thread.last_message_preview || "No messages yet"}</div>
                    <div className="mt-1 text-[10px] text-slate-400">{formatRelativeDate(thread.last_message_at || thread.updated_at)}</div>
                  </button>
                );
              })}
            </div>
          </div>
        </section>

        <section className="flex min-w-0 flex-1 flex-col">
          <header className="border-b border-slate-200 px-4 py-3">
            <div className="text-sm font-semibold text-slate-900">Tanner Assistant</div>
            <div className="text-xs text-slate-500">Context: {context.module} | {context.path}</div>
            <div className="mt-2 flex flex-wrap gap-2">
              {QUICK_ACTIONS.map((action) => (
                <button
                  key={action.value}
                  type="button"
                  onClick={() => handleQuickAction(action.value, action.seed)}
                  className={`rounded-full border px-3 py-1 text-xs transition-colors ${
                    pendingQuickAction === action.value
                      ? "border-cyan-300 bg-cyan-50 text-cyan-700"
                      : "border-slate-200 bg-white text-slate-600 hover:border-slate-300"
                  }`}
                >
                  {action.label}
                </button>
              ))}
            </div>
          </header>

          <div ref={historyRef} className="flex-1 space-y-3 overflow-y-auto bg-white px-4 py-4">
            {isLoadingMessages ? <div className="text-xs text-slate-500">Loading messages...</div> : null}
            {!isLoadingMessages && !messages.length ? <div className="text-xs text-slate-500">Start a new message to open a thread.</div> : null}
            {messages.map((message) => (
              <div key={message.id} className={`max-w-[92%] rounded-xl px-3 py-2 text-sm ${messageBubbleClass(message.role)}`}>
                <div className="whitespace-pre-wrap break-words">{message.content}</div>
                <div className="mt-1 text-[10px] opacity-70">{formatRelativeDate(message.created_at)}</div>
              </div>
            ))}
          </div>

          <footer className="border-t border-slate-200 p-4">
            {error ? <div className="mb-2 rounded-md border border-rose-200 bg-rose-50 px-2 py-1 text-xs text-rose-700">{error}</div> : null}
            <form onSubmit={handleSend} className="flex items-end gap-2">
              <textarea
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                placeholder="Ask Tanner..."
                rows={2}
                className="min-h-[72px] flex-1 resize-y rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-800 focus:border-slate-300 focus:outline-none focus:ring-2 focus:ring-slate-200"
              />
              <button
                type="submit"
                disabled={isSending || !draft.trim()}
                className="h-10 rounded-lg bg-slate-900 px-4 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60"
              >
                {isSending ? "Sending..." : "Send"}
              </button>
            </form>
          </footer>
        </section>
      </aside>
    </>
  );
}
