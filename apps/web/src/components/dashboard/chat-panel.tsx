"use client";

import { Send, Sparkles, User } from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useRef, useState } from "react";
import { api, type ChatMessage, type Filter } from "@/lib/api";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

type Props = { filter: Filter };

const SUGGESTED = [
  "What is my biggest leak right now?",
  "Where is my edge coming from by strategy, DTE and underlying?",
  "Which trade family is hurting expectancy the most?",
  "Compare winners versus losers and find repeated patterns.",
];

export function ChatPanel({ filter }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [provider, setProvider] = useState<"anthropic" | "openai">("anthropic");
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, streaming]);

  async function send(prompt?: string) {
    const text = (prompt ?? input).trim();
    if (!text || streaming) return;
    const userMsg: ChatMessage = { role: "user", content: text };
    const next = [...messages, userMsg];
    setMessages([...next, { role: "assistant", content: "" }]);
    setInput("");
    setStreaming(true);

    try {
      await api.chat(next, filter, provider, (delta) => {
        setMessages((cur) => {
          const copy = [...cur];
          const last = copy[copy.length - 1];
          if (last?.role === "assistant") copy[copy.length - 1] = { ...last, content: last.content + delta };
          return copy;
        });
      });
    } catch (e) {
      setMessages((cur) => {
        const copy = [...cur];
        const last = copy[copy.length - 1];
        if (last?.role === "assistant" && !last.content) {
          copy[copy.length - 1] = { ...last, content: `[error] ${e instanceof Error ? e.message : String(e)}` };
        }
        return copy;
      });
    } finally {
      setStreaming(false);
    }
  }

  return (
    <div className="flex h-[620px] flex-col overflow-hidden rounded-2xl border border-border/40 bg-card/30 lg:h-[calc(100vh-7rem)] lg:max-h-[760px] lg:min-h-[560px]">
      <div className="flex items-center justify-between border-b border-border/30 px-5 py-3.5">
        <div className="flex items-center gap-2">
          <Sparkles className="h-3.5 w-3.5 text-accent/80" />
          <h3 className="text-[13px] font-semibold tracking-tight">Portfolio AI</h3>
          <span className="text-[10px] uppercase tracking-wider text-muted-foreground/70">
            · {filter.months.length ? filter.months.join(", ") : "ALL"}
          </span>
        </div>
        <Select value={provider} onValueChange={(v) => setProvider(v as "anthropic" | "openai")}>
          <SelectTrigger className="h-7 w-[92px] border-border/60 bg-card/40 text-[11px] focus:border-primary/60">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="anthropic" className="text-xs">Claude</SelectItem>
            <SelectItem value="openai" className="text-xs">GPT</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
        {messages.length === 0 ? (
          <div className="flex h-full flex-col justify-center gap-4">
            <div className="text-center">
              <div className="mx-auto mb-2 flex h-12 w-12 items-center justify-center rounded-full bg-gradient-to-br from-primary/20 to-accent/20 ring-1 ring-primary/30">
                <Sparkles className="h-5 w-5 text-primary" />
              </div>
              <h4 className="text-sm font-medium">Analyze the portfolio in scope</h4>
              <p className="mt-1 text-xs text-muted-foreground">
                I see {filter.months.length ? filter.months.join(", ") : "all months"}. Ask anything quantitative.
              </p>
            </div>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {SUGGESTED.map((s) => (
                <button
                  key={s}
                  onClick={() => send(s)}
                  className="rounded-lg border border-border/60 bg-card/40 px-3 py-2 text-left text-xs text-muted-foreground transition hover:border-primary/40 hover:bg-card hover:text-foreground"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            {messages.map((m, i) => (
              <div key={i} className={`flex gap-3 fade-in ${m.role === "user" ? "justify-end" : ""}`}>
                {m.role === "assistant" && (
                  <div className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-primary/30 to-accent/30 ring-1 ring-primary/40">
                    <Sparkles className="h-3.5 w-3.5 text-primary" />
                  </div>
                )}
                <div
                  className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
                    m.role === "user"
                      ? "bg-primary text-primary-foreground"
                      : "border border-border/60 bg-card/70"
                  }`}
                >
                  {m.content ? (
                    m.role === "assistant" ? <MarkdownMessage content={m.content} /> : m.content
                  ) : (
                    <span className="inline-flex gap-1"><Dot /><Dot delay={150} /><Dot delay={300} /></span>
                  )}
                </div>
                {m.role === "user" && (
                  <div className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-muted">
                    <User className="h-3.5 w-3.5 text-muted-foreground" />
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          send();
        }}
        className="border-t border-border/60 p-3"
      >
        <div className="flex items-center gap-2 rounded-lg border border-border/60 bg-card/40 px-3 py-2 focus-within:border-primary/60">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about leaks, correlations, exposure…"
            disabled={streaming}
            className="flex-1 bg-transparent text-sm placeholder:text-muted-foreground focus:outline-none disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={streaming || !input.trim()}
            className="flex h-7 w-7 items-center justify-center rounded-md bg-primary text-primary-foreground transition hover:opacity-90 disabled:opacity-30"
            aria-label="Send"
          >
            <Send className="h-3.5 w-3.5" />
          </button>
        </div>
      </form>
    </div>
  );
}

function MarkdownMessage({ content }: { content: string }) {
  const lines = content.split(/\r?\n/);
  const nodes: ReactNode[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i].trim();
    if (!line) {
      i += 1;
      continue;
    }

    if (line.startsWith("|") && line.endsWith("|")) {
      const tableLines: string[] = [];
      while (i < lines.length && lines[i].trim().startsWith("|") && lines[i].trim().endsWith("|")) {
        tableLines.push(lines[i].trim());
        i += 1;
      }
      nodes.push(<MarkdownTable key={nodes.length} lines={tableLines} />);
      continue;
    }

    const heading = line.match(/^(#{1,4})\s+(.+)$/);
    if (heading) {
      nodes.push(
        <div key={nodes.length} className="mt-3 first:mt-0 text-[13px] font-semibold text-foreground">
          {renderInline(heading[2])}
        </div>,
      );
      i += 1;
      continue;
    }

    if (/^[-*]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^[-*]\s+/.test(lines[i].trim())) {
        items.push(lines[i].trim().replace(/^[-*]\s+/, ""));
        i += 1;
      }
      nodes.push(
        <ul key={nodes.length} className="my-2 space-y-1.5 pl-4 text-muted-foreground">
          {items.map((item, idx) => <li key={idx} className="list-disc">{renderInline(item)}</li>)}
        </ul>,
      );
      continue;
    }

    if (/^\d+\.\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\d+\.\s+/.test(lines[i].trim())) {
        items.push(lines[i].trim().replace(/^\d+\.\s+/, ""));
        i += 1;
      }
      nodes.push(
        <ol key={nodes.length} className="my-2 space-y-1.5 pl-4 text-muted-foreground">
          {items.map((item, idx) => <li key={idx} className="list-decimal">{renderInline(item)}</li>)}
        </ol>,
      );
      continue;
    }

    const paragraph: string[] = [];
    while (
      i < lines.length &&
      lines[i].trim() &&
      !/^(#{1,4})\s+/.test(lines[i].trim()) &&
      !/^[-*]\s+/.test(lines[i].trim()) &&
      !/^\d+\.\s+/.test(lines[i].trim()) &&
      !(lines[i].trim().startsWith("|") && lines[i].trim().endsWith("|"))
    ) {
      paragraph.push(lines[i].trim());
      i += 1;
    }
    nodes.push(
      <p key={nodes.length} className="my-2 first:mt-0 last:mb-0 text-muted-foreground">
        {renderInline(paragraph.join(" "))}
      </p>,
    );
  }

  return <div className="space-y-1">{nodes}</div>;
}

function MarkdownTable({ lines }: { lines: string[] }) {
  const rows = lines
    .filter((line) => !/^\|\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|$/.test(line))
    .map((line) => line.split("|").slice(1, -1).map((cell) => cell.trim()));

  if (!rows.length) return null;
  const [head, ...body] = rows;
  return (
    <div className="my-3 overflow-x-auto rounded-lg border border-border/60">
      <table className="w-full min-w-[360px] text-left text-xs">
        <thead className="bg-background/35 text-foreground">
          <tr>{head.map((cell, idx) => <th key={idx} className="px-2.5 py-2 font-semibold">{renderInline(cell)}</th>)}</tr>
        </thead>
        <tbody className="divide-y divide-border/50 text-muted-foreground">
          {body.map((row, rowIdx) => (
            <tr key={rowIdx}>
              {row.map((cell, cellIdx) => <td key={cellIdx} className="px-2.5 py-2 align-top">{renderInline(cell)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function renderInline(text: string): ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, idx) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={idx} className="font-semibold text-foreground">{part.slice(2, -2)}</strong>;
    }
    return <span key={idx}>{part}</span>;
  });
}

function Dot({ delay = 0 }: { delay?: number }) {
  return (
    <span
      className="inline-block h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground"
      style={{ animationDelay: `${delay}ms` }}
    />
  );
}
