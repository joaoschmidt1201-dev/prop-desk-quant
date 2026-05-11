"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { LayoutGrid } from "lucide-react";
import {
  api,
  type ForwardtestAggDim,
  type ForwardtestAggregationRow,
  type ForwardtestEnv,
} from "@/lib/api";
import { fmtMoney, fmtNum, fmtPct, pnlClass } from "@/lib/format";
import { DASHBOARD_REFETCH_INTERVAL_MS } from "@/lib/refresh";

const DIM_LABELS: Record<ForwardtestAggDim, string> = {
  family: "By Family",
  ticker: "By Ticker",
  structure: "By Structure",
};

const DIM_KEY_LABELS: Record<ForwardtestAggDim, string> = {
  family: "Family",
  ticker: "Underlying",
  structure: "DTE / Structure",
};

type Props = {
  env: ForwardtestEnv;
};

export function AggregationsTable({ env }: Props) {
  const [dim, setDim] = useState<ForwardtestAggDim>("family");
  const { data, isLoading } = useQuery({
    queryKey: ["forwardtests", "aggregations", env, dim],
    queryFn: () => api.forwardtestsAggregations(env, dim),
    refetchInterval: DASHBOARD_REFETCH_INTERVAL_MS,
  });

  const rows = data?.rows ?? [];

  return (
    <section className="rounded-2xl border border-border/60 bg-gradient-to-b from-card/70 to-card/35 p-5 shadow-2xl shadow-black/10">
      <Header dim={dim} onDimChange={setDim} />

      {isLoading ? (
        <div className="h-[200px] animate-pulse rounded-xl border border-dashed border-border/50 bg-card/20" />
      ) : rows.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border/50 bg-card/20 p-6 text-center text-[12px] text-muted-foreground">
          No forward trades to aggregate yet.
        </div>
      ) : (
        <AggTable rows={rows} keyLabel={DIM_KEY_LABELS[dim]} />
      )}
    </section>
  );
}

function Header({ dim, onDimChange }: { dim: ForwardtestAggDim; onDimChange: (d: ForwardtestAggDim) => void }) {
  return (
    <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
      <div className="flex items-center gap-2">
        <span className="text-primary">
          <LayoutGrid className="h-4 w-4" />
        </span>
        <h3 className="text-sm font-semibold tracking-tight">Cross-strategy aggregations</h3>
        <span className="ml-2 text-[11px] text-muted-foreground">slice the lab by family, ticker, or structure</span>
      </div>
      <div className="inline-flex overflow-hidden rounded-md border border-border/50 bg-card/20 p-0.5">
        {(Object.keys(DIM_LABELS) as ForwardtestAggDim[]).map((d) => {
          const active = dim === d;
          return (
            <button
              key={d}
              onClick={() => onDimChange(d)}
              className={`rounded px-3 py-1 text-[11px] font-semibold transition ${
                active
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-card/60 hover:text-foreground"
              }`}
            >
              {DIM_LABELS[d]}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function AggTable({ rows, keyLabel }: { rows: ForwardtestAggregationRow[]; keyLabel: string }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[860px] text-[12px]">
        <thead>
          <tr className="border-b border-border/50 text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
            <Th className="text-left">{keyLabel}</Th>
            <Th>Trades</Th>
            <Th>Open / Closed</Th>
            <Th>Win rate</Th>
            <Th>Profit factor</Th>
            <Th>Total P&L</Th>
            <Th>Avg DIT → 10%</Th>
            <Th>Avg DIT → 25%</Th>
            <Th>Avg DIT → 50%</Th>
            <Th>Avg DIT → 75%</Th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.key} className="border-b border-border/30 last:border-0 hover:bg-card/30">
              <td className="py-2.5 pr-3 text-left text-sm font-medium">{r.key}</td>
              <Td>{r.n_trades_total}</Td>
              <Td>
                <span className="tabular">{r.n_trades_open}</span>
                <span className="mx-1 text-muted-foreground">/</span>
                <span className="tabular">{r.n_trades_closed}</span>
              </Td>
              <Td>{r.win_rate != null ? fmtPct(r.win_rate) : "—"}</Td>
              <Td>{r.profit_factor != null ? fmtNum(r.profit_factor) : "—"}</Td>
              <Td className={pnlClass(r.total_pnl)}>{fmtMoney(r.total_pnl)}</Td>
              <Td>{r.avg_dit_to_10mp != null ? `${r.avg_dit_to_10mp}d` : "—"}</Td>
              <Td>{r.avg_dit_to_25mp != null ? `${r.avg_dit_to_25mp}d` : "—"}</Td>
              <Td>{r.avg_dit_to_50mp != null ? `${r.avg_dit_to_50mp}d` : "—"}</Td>
              <Td>{r.avg_dit_to_75mp != null ? `${r.avg_dit_to_75mp}d` : "—"}</Td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Th({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <th className={`py-2 px-2 font-medium ${className || "text-right"}`}>{children}</th>;
}

function Td({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <td className={`py-2.5 px-2 text-right tabular ${className}`}>{children}</td>;
}
