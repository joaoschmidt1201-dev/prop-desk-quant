"use client";

import { Download } from "lucide-react";
import { useState } from "react";
import { api, type Filter } from "@/lib/api";

type Props = { filter: Filter };

export function TradesDownload({ filter }: Props) {
  const [status, setStatus] = useState<"idle" | "loading" | "error">("idle");

  async function downloadTrades() {
    if (status === "loading") return;
    setStatus("loading");
    try {
      const [health, kpis, trades, analytics] = await Promise.all([
        api.health(),
        api.kpis(filter),
        api.trades(filter),
        api.analytics(filter),
      ]);
      const payload = {
        exported_at: new Date().toISOString(),
        source: "ST Options Control Panel",
        snapshot_generated_at: health.snapshot_generated_at,
        filter: trades.filter,
        kpis,
        analytics: {
          summary: analytics.summary,
          by_month: analytics.by_month,
          by_strategy: analytics.by_strategy,
          by_underlying: analytics.by_underlying,
          by_dte_bucket: analytics.by_dte_bucket,
          by_weekday: analytics.by_weekday,
          by_day: analytics.by_day,
          by_close_weekday: analytics.by_close_weekday,
          top_winners: analytics.top_winners,
          top_losers: analytics.top_losers,
          insights: analytics.insights,
        },
        trades: trades.trades,
      };

      const scope = filter.months.length ? filter.months.join("_") : "ALL";
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `st-trades-ai-export-${scope}-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      setStatus("idle");
    } catch (error) {
      console.error("Trade export failed", error);
      setStatus("error");
    }
  }

  return (
    <div className="mt-7 flex justify-end">
      <button
        type="button"
        onClick={downloadTrades}
        disabled={status === "loading"}
        className="inline-flex h-10 items-center gap-2 rounded-full border border-border/50 bg-card/35 px-4 text-xs font-medium text-muted-foreground transition hover:border-primary/40 hover:bg-card/60 hover:text-foreground disabled:cursor-wait disabled:opacity-60"
      >
        <Download className="h-3.5 w-3.5" />
        <span>{status === "loading" ? "Preparing export" : status === "error" ? "Retry download" : "Download trades JSON"}</span>
      </button>
    </div>
  );
}
