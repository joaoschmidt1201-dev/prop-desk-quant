"use client";

import Link from "next/link";
import { Activity } from "lucide-react";
import type { ForwardtestRecentEntry } from "@/lib/api";
import { fmtDate, fmtMoney, pnlClass } from "@/lib/format";

type Props = {
  entries: ForwardtestRecentEntry[];
};

export function RecentActivity({ entries }: Props) {
  return (
    <section className="rounded-2xl border border-border/60 bg-gradient-to-b from-card/70 to-card/35 p-5 shadow-2xl shadow-black/10">
      <div className="mb-4 flex items-center gap-2">
        <span className="text-primary"><Activity className="h-4 w-4" /></span>
        <h3 className="text-sm font-semibold tracking-tight">Recent activity</h3>
        <span className="ml-2 text-[11px] text-muted-foreground">last marks across the lab</span>
      </div>
      {entries.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border/50 bg-card/20 p-6 text-center text-[12px] text-muted-foreground">
          No forward trades yet — first mark from db_robots will land here.
        </div>
      ) : (
        <ul className="divide-y divide-border/30">
          {entries.map((e, idx) => (
            <li key={`${e.trade_name}-${idx}`}>
              <Link
                href={`/forwardtests/${encodeURIComponent(e.strategy_id)}`}
                className="flex items-center gap-3 rounded-md px-2 py-2.5 transition hover:bg-card/40"
              >
                <Badge kind={e.kind} />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[13px] font-medium">{e.trade_name}</div>
                  <div className="mt-0.5 truncate text-[10px] text-muted-foreground">
                    {e.strategy_name}
                  </div>
                </div>
                <div className="text-right">
                  <div className={`tabular text-sm font-semibold ${pnlClass(e.pnl)}`}>
                    {fmtMoney(e.pnl)}
                  </div>
                  <div className="text-[10px] text-muted-foreground">
                    {fmtDate(e.event_date)}
                  </div>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Badge({ kind }: { kind: "open" | "closed" }) {
  const isOpen = kind === "open";
  return (
    <span
      className={`inline-flex shrink-0 items-center justify-center rounded-md px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${
        isOpen
          ? "border border-primary/30 bg-primary/10 text-primary"
          : "border border-border/60 bg-background/40 text-muted-foreground"
      }`}
    >
      {kind}
    </span>
  );
}
