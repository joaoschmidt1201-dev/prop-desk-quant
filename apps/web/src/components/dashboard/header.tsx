"use client";

import type { QueryClient } from "@tanstack/react-query";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { fmtRelativeAge } from "@/lib/format";
import { DASHBOARD_REFETCH_INTERVAL_MS } from "@/lib/refresh";

const DASHBOARD_DATA_QUERY_KEYS = ["months", "kpis", "trades", "analytics"] as const;

function invalidateDashboardData(queryClient: QueryClient) {
  return Promise.all(
    DASHBOARD_DATA_QUERY_KEYS.map((queryKey) => queryClient.invalidateQueries({ queryKey: [queryKey] })),
  );
}

export function DashboardHeader() {
  const queryClient = useQueryClient();
  const [isRefreshing, setIsRefreshing] = useState(false);
  const lastSnapshotGeneratedAt = useRef<string | null | undefined>(undefined);
  const { data, refetch, isFetching } = useQuery({
    queryKey: ["health"],
    queryFn: () => api.health(),
    refetchInterval: DASHBOARD_REFETCH_INTERVAL_MS,
    refetchIntervalInBackground: true,
  });
  const spinning = isFetching || isRefreshing;

  useEffect(() => {
    const currentGeneratedAt = data?.snapshot_generated_at ?? null;
    if (lastSnapshotGeneratedAt.current === undefined) {
      lastSnapshotGeneratedAt.current = currentGeneratedAt;
      return;
    }
    if (currentGeneratedAt && currentGeneratedAt !== lastSnapshotGeneratedAt.current) {
      lastSnapshotGeneratedAt.current = currentGeneratedAt;
      void invalidateDashboardData(queryClient);
      return;
    }
    lastSnapshotGeneratedAt.current = currentGeneratedAt;
  }, [data?.snapshot_generated_at, queryClient]);

  async function handleRefresh() {
    if (isRefreshing) return;
    setIsRefreshing(true);
    const initialGeneratedAt = data?.snapshot_generated_at ?? null;
    try {
      await api.refreshSnapshot();
      // Poll /api/health for up to 60s until snapshot_generated_at advances.
      const deadline = Date.now() + 60_000;
      let advanced = false;
      while (Date.now() < deadline) {
        await new Promise((r) => setTimeout(r, 1_500));
        try {
          const fresh = await api.health();
          if (fresh.snapshot_generated_at && fresh.snapshot_generated_at !== initialGeneratedAt) {
            advanced = true;
            break;
          }
        } catch {
          // transient — keep polling
        }
      }
      await Promise.all([
        refetch(),
        invalidateDashboardData(queryClient),
      ]);
      if (!advanced) console.warn("Snapshot refresh did not advance within 60s");
    } catch (e) {
      console.error("Snapshot refresh failed", e);
    } finally {
      setIsRefreshing(false);
    }
  }

  return (
    <header className="sticky top-0 z-30 border-b border-border/40 bg-background/60 backdrop-blur-xl">
      <div className="mx-auto flex max-w-[1600px] items-center justify-between px-8 py-5">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Options Control Panel</h1>
          <p className="mt-0.5 text-xs text-muted-foreground">Live positions reconciled with the visual sheet · zero execution</p>
        </div>

        <div className="flex items-center gap-2">
          <div className="flex items-center gap-2 rounded-full border border-border/40 bg-card/30 px-3 py-1 text-[11px]">
            <span className="h-1.5 w-1.5 rounded-full bg-[var(--gain)]" />
            <span className="tabular text-muted-foreground">{fmtRelativeAge(data?.snapshot_age_seconds)}</span>
          </div>
          <button
            onClick={handleRefresh}
            disabled={spinning}
            className="flex h-8 items-center gap-1.5 rounded-full border border-border/40 bg-card/30 px-3.5 text-[11px] font-medium text-muted-foreground transition hover:border-border hover:bg-card/60 hover:text-foreground disabled:opacity-50"
            aria-label="Refresh"
          >
            <RefreshCw className={`h-3 w-3 ${spinning ? "animate-spin" : ""}`} />
            <span>Refresh</span>
          </button>
        </div>
      </div>
    </header>
  );
}
