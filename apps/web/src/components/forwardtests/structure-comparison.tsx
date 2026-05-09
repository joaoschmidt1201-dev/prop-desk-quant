"use client";

import { GitCompare } from "lucide-react";
import type { ForwardtestStructureGroup } from "@/lib/api";
import { fmtMoney, fmtPct, fmtNum, pnlClass } from "@/lib/format";

type Props = {
  groups: ForwardtestStructureGroup[];
};

export function StructureComparison({ groups }: Props) {
  if (groups.length === 0) {
    return (
      <section className="rounded-2xl border border-border/60 bg-gradient-to-b from-card/70 to-card/35 p-5 shadow-2xl shadow-black/10">
        <Header />
        <div className="rounded-xl border border-dashed border-border/50 bg-card/20 p-6 text-center text-[12px] text-muted-foreground">
          Add a second DTE structure to any tracked family (e.g., Triple Calendar 14/28 alongside 21/28) and the comparison shows up here.
        </div>
      </section>
    );
  }

  return (
    <section className="rounded-2xl border border-border/60 bg-gradient-to-b from-card/70 to-card/35 p-5 shadow-2xl shadow-black/10">
      <Header />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {groups.map((g) => (
          <FamilyCard key={g.family} group={g} />
        ))}
      </div>
    </section>
  );
}

function Header() {
  return (
    <div className="mb-4 flex items-center gap-2">
      <span className="text-primary"><GitCompare className="h-4 w-4" /></span>
      <h3 className="text-sm font-semibold tracking-tight">Structure comparison</h3>
      <span className="ml-2 text-[11px] text-muted-foreground">which DTE configuration is winning per family</span>
    </div>
  );
}

function FamilyCard({ group }: { group: ForwardtestStructureGroup }) {
  const maxAbsPnl = Math.max(1, ...group.structures.map((s) => Math.abs(s.total_pnl)));

  return (
    <div className="rounded-xl border border-border/50 bg-background/30 p-4">
      <div className="mb-3 text-sm font-semibold">{group.family}</div>
      <div className="space-y-2.5">
        {group.structures.map((s) => {
          const widthPct = Math.min(100, (Math.abs(s.total_pnl) / maxAbsPnl) * 100);
          return (
            <div key={s.structure ?? "any"}>
              <div className="flex items-baseline justify-between gap-3 text-[12px]">
                <span className="font-medium">
                  {s.structure ? structureLabel(s.structure) : "any DTE"}
                  <span className="ml-2 text-[10px] text-muted-foreground">
                    {s.underlyings.join(" · ") || "—"}
                  </span>
                </span>
                <span className={`tabular text-sm font-semibold ${pnlClass(s.total_pnl)}`}>
                  {fmtMoney(s.total_pnl)}
                </span>
              </div>
              <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-border/40">
                <div
                  className={`h-full rounded-full ${s.total_pnl >= 0 ? "bg-[var(--gain)]/70" : "bg-[var(--loss)]/70"}`}
                  style={{ width: `${widthPct}%` }}
                />
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-0.5 text-[10px] text-muted-foreground">
                <span>WR {s.win_rate != null ? fmtPct(s.win_rate) : "—"}</span>
                <span>median DIT→50% {s.median_dit_to_50mp != null ? `${fmtNum(s.median_dit_to_50mp)}d` : "—"}</span>
                <span>{s.n_open} open · {s.n_closed} closed</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function structureLabel(s: string): string {
  return s.includes("/") ? `${s} DTE` : `${s} DTE`;
}
