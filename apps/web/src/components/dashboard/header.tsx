"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, RefreshCw } from "lucide-react";
import { useState } from "react";
import { api } from "@/lib/api";
import { fmtRelativeAge } from "@/lib/format";

export function DashboardHeader() {
  const queryClient = useQueryClient();
  const [isRefreshing, setIsRefreshing] = useState(false);
  const { data, refetch, isFetching } = useQuery({
    queryKey: ["health"],
    queryFn: () => api.health(),
    refetchInterval: 60_000,
  });
  const spinning = isFetching || isRefreshing;

  async function handleRefresh() {
    if (isRefreshing) return;
    setIsRefreshing(true);
    try {
      await api.refreshSnapshot();
      await new Promise((resolve) => setTimeout(resolve, 8_000));
      await Promise.all([
        refetch(),
        queryClient.invalidateQueries({ queryKey: ["months"] }),
        queryClient.invalidateQueries({ queryKey: ["kpis"] }),
        queryClient.invalidateQueries({ queryKey: ["trades"] }),
      ]);
    } catch (e) {
      console.error("Snapshot refresh failed", e);
    } finally {
      setIsRefreshing(false);
    }
  }

  return (
    <header className="sticky top-0 z-30 border-b border-border/60 bg-background/70 backdrop-blur-md">
      <div className="mx-auto flex max-w-[1600px] items-center justify-between px-6 py-4">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-primary/30 to-accent/30 ring-1 ring-primary/40">
            <Activity className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h1 className="text-base font-semibold tracking-tight">CZ Dashboard</h1>
            <p className="text-xs text-muted-foreground">Options Control Panel · Prop Desk</p>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 rounded-md border border-border/60 bg-card/40 px-3 py-1.5 text-xs">
            <span className="relative inline-flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full rounded-full bg-[var(--gain)] opacity-60 animate-ping" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-[var(--gain)]" />
            </span>
            <span className="text-muted-foreground">snapshot</span>
            <span className="tabular text-foreground">{fmtRelativeAge(data?.snapshot_age_seconds)}</span>
          </div>
          <button
            onClick={handleRefresh}
            disabled={spinning}
            className="flex h-8 w-8 items-center justify-center rounded-md border border-border/60 bg-card/40 text-muted-foreground transition hover:bg-card hover:text-foreground disabled:opacity-50"
            aria-label="Refresh"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${spinning ? "animate-spin" : ""}`} />
          </button>
        </div>
      </div>
    </header>
  );
}
