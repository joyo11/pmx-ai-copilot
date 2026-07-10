"use client";

import * as React from "react";
import { useAuth } from "@clerk/nextjs";
import { Send, FileText, Sparkles, AlertTriangle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { sendChatMessage, ApiError, type Citation } from "@/lib/api";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  streaming?: boolean;
  error?: string;
}

function makeId(): string {
  // Cheap unique id; nothing security-sensitive rides on this.
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export function ChatPanel({ projectId }: { projectId: string }) {
  const { getToken } = useAuth();
  const [messages, setMessages] = React.useState<Message[]>([]);
  const [sources, setSources] = React.useState<Citation[]>([]);
  const [input, setInput] = React.useState("");
  const [sending, setSending] = React.useState(false);
  const [sessionId, setSessionId] = React.useState<string | undefined>(
    undefined
  );
  const abortRef = React.useRef<AbortController | null>(null);
  const scrollRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages]);

  React.useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || sending) return;

    const userMsg: Message = {
      id: makeId(),
      role: "user",
      content: trimmed,
    };
    const assistantId = makeId();
    const assistantMsg: Message = {
      id: assistantId,
      role: "assistant",
      content: "",
      citations: [],
      streaming: true,
    };
    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setInput("");
    setSending(true);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const token = await getToken();
      const stream = sendChatMessage(
        { projectId, message: trimmed, sessionId },
        { token, signal: controller.signal }
      );

      for await (const evt of stream) {
        if (evt.type === "token") {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? { ...m, content: m.content + evt.text }
                : m
            )
          );
        } else if (evt.type === "citation") {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? {
                    ...m,
                    citations: dedupeCitations([
                      ...(m.citations ?? []),
                      evt.citation,
                    ]),
                  }
                : m
            )
          );
          setSources((prev) => dedupeCitations([...prev, evt.citation]));
        } else if (evt.type === "done") {
          if (evt.session_id) setSessionId(evt.session_id);
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId ? { ...m, streaming: false } : m
            )
          );
        } else if (evt.type === "error") {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? { ...m, streaming: false, error: evt.message }
                : m
            )
          );
        }
      }
      // Stream ended without an explicit `done` event.
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId ? { ...m, streaming: false } : m
        )
      );
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? `API ${err.status}: ${err.body ?? err.message}`
          : err instanceof Error
            ? err.message
            : "Chat failed";
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? { ...m, streaming: false, error: msg }
            : m
        )
      );
    } finally {
      abortRef.current = null;
      setSending(false);
    }
  }

  const [mobileTab, setMobileTab] = React.useState<"chat" | "sources">("chat");

  const conversation = (
    <div className="flex h-[calc(100svh-20rem)] lg:h-[calc(100svh-16rem)] flex-col rounded-xl border">
      <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto p-4">
        {messages.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
            <div className="flex size-12 items-center justify-center rounded-full bg-muted">
              <Sparkles className="size-5 text-muted-foreground" />
            </div>
            <div className="max-w-sm space-y-1">
              <p className="text-sm font-medium">Ask about this project</p>
              <p className="text-xs text-muted-foreground">
                Grounded in the documents you upload. Citations appear beside
                each answer as it streams in.
              </p>
            </div>
          </div>
        ) : (
          messages.map((m) => <MessageBubble key={m.id} message={m} />)
        )}
      </div>
      <form
        onSubmit={onSubmit}
        className="flex items-center gap-2 border-t p-3"
        style={{ paddingBottom: "max(0.75rem, env(safe-area-inset-bottom))" }}
      >
        <Input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about risks, budget, schedule…"
          disabled={sending}
          className="text-base md:text-sm"
        />
        <Button
          type="submit"
          size="icon"
          className="size-11 md:size-9"
          disabled={sending || !input.trim()}
        >
          <Send className="size-4" />
          <span className="sr-only">Send</span>
        </Button>
      </form>
    </div>
  );

  const sourcesPanel = (
    <aside className="rounded-xl border p-4">
      <h3 className="mb-3 text-sm font-semibold">Sources</h3>
      {sources.length === 0 ? (
        <p className="text-xs text-muted-foreground">
          Citations appear here as the assistant answers.
        </p>
      ) : (
        <ul className="space-y-2">
          {sources.map((c, i) => (
            <li key={citationKey(c) + i}>
              <CitationChip citation={c} />
            </li>
          ))}
        </ul>
      )}
    </aside>
  );

  return (
    <div>
      {/* Mobile: tab switcher */}
      <div className="mb-3 flex gap-1 rounded-lg border p-1 lg:hidden">
        <button
          type="button"
          onClick={() => setMobileTab("chat")}
          className={cn(
            "flex-1 rounded-md py-2 text-sm font-medium transition-colors",
            mobileTab === "chat"
              ? "bg-primary text-primary-foreground"
              : "text-muted-foreground"
          )}
        >
          Chat
        </button>
        <button
          type="button"
          onClick={() => setMobileTab("sources")}
          className={cn(
            "flex-1 rounded-md py-2 text-sm font-medium transition-colors",
            mobileTab === "sources"
              ? "bg-primary text-primary-foreground"
              : "text-muted-foreground"
          )}
        >
          Sources
          {sources.length > 0 ? (
            <span className="ml-1.5 rounded bg-muted px-1.5 text-xs tabular-nums">
              {sources.length}
            </span>
          ) : null}
        </button>
      </div>

      <div className="lg:grid lg:grid-cols-[1fr_320px] lg:gap-4">
        {/* Show chat + sources side-by-side on lg, tabbed on mobile */}
        <div className={cn("lg:block", mobileTab === "chat" ? "block" : "hidden")}>
          {conversation}
        </div>
        <div className={cn("lg:block", mobileTab === "sources" ? "block" : "hidden")}>
          {sourcesPanel}
        </div>
      </div>
    </div>
  );
}

function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === "user";
  return (
    <div
      className={cn(
        "flex flex-col gap-2",
        isUser ? "items-end" : "items-start"
      )}
    >
      <div
        className={cn(
          "max-w-[85%] whitespace-pre-wrap rounded-lg px-3 py-2 text-sm",
          isUser
            ? "bg-primary text-primary-foreground"
            : "bg-muted text-foreground"
        )}
      >
        {message.content || (message.streaming ? "…" : "")}
        {message.streaming ? (
          <span className="ml-0.5 inline-block h-4 w-1.5 -translate-y-0.5 animate-pulse bg-current align-middle" />
        ) : null}
      </div>
      {message.error ? (
        <div className="flex items-center gap-1.5 text-xs text-destructive">
          <AlertTriangle className="size-3" /> {message.error}
        </div>
      ) : null}
      {!isUser && message.citations && message.citations.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {message.citations.map((c, i) => (
            <CitationChip key={citationKey(c) + i} citation={c} inline />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function CitationChip({
  citation,
  inline,
}: {
  citation: Citation;
  inline?: boolean;
}) {
  const label = citation.document_filename ?? citation.document_id;
  const page =
    typeof citation.page === "number" ? `p.${citation.page}` : null;
  return (
    <Badge
      variant={inline ? "outline" : "secondary"}
      className="gap-1 font-normal"
    >
      <FileText className="size-3" />
      <span className="max-w-[180px] truncate">{label}</span>
      {page ? (
        <span className="text-muted-foreground tabular-nums">{page}</span>
      ) : null}
    </Badge>
  );
}

function citationKey(c: Citation): string {
  return `${c.document_id}:${c.chunk_id ?? ""}:${c.page ?? ""}`;
}

function dedupeCitations(cs: Citation[]): Citation[] {
  const seen = new Set<string>();
  const out: Citation[] = [];
  for (const c of cs) {
    const k = citationKey(c);
    if (seen.has(k)) continue;
    seen.add(k);
    out.push(c);
  }
  return out;
}
