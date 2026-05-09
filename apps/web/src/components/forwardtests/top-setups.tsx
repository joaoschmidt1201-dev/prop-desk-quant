"use client";

import Link from "next/link";
import { Trophy, DollarSign, Zap } from "lucide-react";
import type { ForwardtestMatrixCell } from "@/lib/api";
import { fmtMoney, fmtPct, fmtNum, pnlClass } from "@/lib/format";

type Props = {
  topWinrate: ForwardtestMatrixCell[];
  topPnl: ForwardtestMatrixCell[];
  topSpeed: ForwardtestMatrixCell[];
};

export function TopSetups({ topWinrate, topPnl, topSpeed }: Props) {
  return (
    <section className="rounded-2xl border border-border/60 bg-gradient-to-b from-card/70 to-card/35 p-5 shadow-2xl shadow-black/10">
      <div className="mb-4 flex items-center gap-2">
        <span className="text-primary"><Trophy className="h-4 w-4" /></span>
        <h3 className="text-sm font-semibold tracking-tight">Top setups</h3>
        <span className="ml-2 text-[11px] text-muted-foreground">crown the candidates worth scaling into live</span>
      </div>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <Column
          title="Win rate"
          icon={<Trophy className="h-3.5 w-3.5" />}
          items={topWinrate}
          render={(c) => (
            <span className="tabular text-sm font-semibold text-foreground">
              {c.win_rate != null ? fmtPct(c.win_rate) : "—"}
            </span>
          )}
        />
        <Column
          title="Total P&L"
          icon={<DollarSign className="h-3.5 w-3.5" />}
          items={topPnl}
          render={(c) => (
            <span className={`tabular text-sm font-semibold ${pnlClass(c.total_pnl)}`}>
              {fmtMoney(c.total_pnl)}
            </span>
          )}
        />
        <Column
          title="Time to 50% MP"
          icon={<Zap className="h-3.5 w-3.5" />}
          items={topSpeed}
          render={(c) => (
            <span className="tabular text-sm font-semibold text-foreground">
              {c.median_dit_to_50mp != null ? `${fmtNum(c.median_dit_to_50mp)}d` : "—"}
            </span>
          )}
        />
      </div>
    </section>
  );
}

type ColumnProps = {
  title: string;
  icon: React.ReactNode;
  items: ForwardtestMatrixCell[];
  render: (c: ForwardtestMatrixCell) => React.ReactNode;
};

function Column({ title, icon, items, render }: ColumnProps) {
  return (
    <div className="rounded-xl border border-border/50 bg-background/30 p-4">
      <div className="mb-3 flex items-center gap-1.5 text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
        <span className="text-foreground/70">{icon}</span>
        {title}
      </div>
      {items.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border/40 bg-card/20 px-3 py-4 text-center text-[11px] text-muted-foreground">
          Awaiting closed trades
        </div>
      ) : (
        <ol className="space-y-1.5">
          {items.map((c, idx) => (
            <li key={c.strategy_id}>
              <Link
                href={`/forwardtests/${encodeURIComponent(c.strategy_id)}`}
                className="flex items-center gap-3 rounded-lg px-2.5 py-2 transition hover:bg-card/40"
              >
                <span className="w-4 text-center text-[10px] font-semibold tabular text-muted-foreground">
                  {idx + 1}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[13px] font-medium">
                    {c.strategy_family ?? "Strategy"} <span className="text-muted-foreground">·</span>{" "}
                    {c.structure ? structureLabel(c.structure) : "any DTE"}
                  </div>
                  <div className="mt-0.5 text-[10px] text-muted-foreground">
                    {c.underlying ?? "?"} · {c.n_closed} closed
                  </div>
                </div>
                {render(c)}
              </Link>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

function structureLabel(s: string): string {
  return s.includes("/") ? `${s} DTE` : `${s} DTE`;
}
