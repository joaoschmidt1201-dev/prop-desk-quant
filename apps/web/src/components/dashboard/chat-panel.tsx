"use client";

import { Send, Sparkles, User } from "lucide-react";
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
  "Which trades are most correlated?",
  "Stress-test the portfolio if RUT drops 5%.",
  "Why is my realized P&L so different from open P&L?",
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
    <div className="flex h-full min-h-[500px] flex-col rounded-xl border border-border/60 bg-card/50">
      <div className="flex items-center justify-between border-b border-border/60 px-5 py-3">
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-accent" />
          <h3 className="text-sm font-semibold tracking-tight">Portfolio AI</h3>
          <span className="text-[11px] text-muted-foreground">
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

      <div ref={scrollRef} className="flex-1 overflow-y-auto px-5 py-4">
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
                  {m.content || <span className="inline-flex gap-1"><Dot /><Dot delay={150} /><Dot delay={300} /></span>}
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

function Dot({ delay = 0 }: { delay?: number }) {
  return (
    <span
      className="inline-block h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground"
      style={{ animationDelay: `${delay}ms` }}
    />
  );
}
