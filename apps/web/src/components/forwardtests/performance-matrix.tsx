"use client";

import Link from "next/link";
import { useMemo } from "react";
import { Grid3x3 } from "lucide-react";
import type { ForwardtestEnv, ForwardtestMatrixCell } from "@/lib/api";
import { fmtMoney, fmtPct, pnlClass } from "@/lib/format";

type Props = {
  cells: ForwardtestMatrixCell[];
  env: ForwardtestEnv;
};

type RowKey = {
  id: string;
  family: string | null;
  structure: string | null;
  label: string;
};

export function PerformanceMatrix({ cells, env }: Props) {
  const { rows, cols, byKey } = useMemo(() => buildAxes(cells), [cells]);

  if (cells.length === 0) {
    return (
      <Section>
        <Empty
          title="Matrix awaits its first forward trade"
          body="Post a trade in OptionStrat — once Make populates db_cria + db_robots and the snapshot refreshes, this matrix lights up with one cell per (family · structure × ticker) combo."
        />
      </Section>
    );
  }

  return (
    <Section>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse">
          <thead>
            <tr>
              <th className="sticky left-0 z-10 bg-card/40 px-3 py-2 text-left text-[10px] font-medium uppercase tracking-[0.2em] text-muted-foreground">
                Family · Structure
              </th>
              {cols.map((u) => (
                <th
                  key={u}
                  className="px-3 py-2 text-center text-[11px] font-semibold tracking-wider text-foreground"
                >
                  {u}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id} className="border-t border-border/30">
                <td className="sticky left-0 z-10 bg-card/40 px-3 py-3 align-middle">
                  <div className="text-sm font-medium">{row.family ?? "Other"}</div>
                  <div className="mt-0.5 text-[11px] text-muted-foreground">
                    {row.structure ? structureLabel(row.structure) : "any DTE"}
                  </div>
                </td>
                {cols.map((u) => {
                  const cell = byKey.get(`${row.id}|${u}`);
                  return (
                    <td key={u} className="p-1.5 align-middle">
                      {cell ? <Cell cell={cell} env={env} /> : <EmptyCell />}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-4 text-[10px] uppercase tracking-wider text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-sm bg-[var(--gain)]/80" /> winning
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-sm bg-[var(--loss)]/80" /> losing
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-sm bg-border/60" /> not tested yet
        </span>
        <span className="ml-auto">click a cell to drill in</span>
      </div>
    </Section>
  );
}

function buildAxes(cells: ForwardtestMatrixCell[]) {
  const rowMap = new Map<string, RowKey>();
  const colSet = new Set<string>();
  const byKey = new Map<string, ForwardtestMatrixCell>();

  for (const c of cells) {
    const family = c.strategy_family ?? "Other";
    const struct = c.structure ?? "—";
    const id = `${family}|${struct}`;
    if (!rowMap.has(id)) {
      rowMap.set(id, { id, family, structure: c.structure, label: family });
    }
    const u = c.underlying ?? "?";
    colSet.add(u);
    byKey.set(`${id}|${u}`, c);
  }

  const rows = Array.from(rowMap.values()).sort((a, b) => {
    const fa = (a.family ?? "").localeCompare(b.family ?? "");
    if (fa !== 0) return fa;
    return structureSortValue(a.structure) - structureSortValue(b.structure);
  });
  const cols = Array.from(colSet).sort();
  return { rows, cols, byKey };
}

function structureSortValue(s: string | null): number {
  if (!s) return 9999;
  const m = s.match(/^(\d+)/);
  return m ? parseInt(m[1], 10) : 9000;
}

function structureLabel(s: string): string {
  return s.includes("/") ? `${s} DTE` : `${s}DTE`;
}

function Cell({ cell, env }: { cell: ForwardtestMatrixCell; env: ForwardtestEnv }) {
  const tone = toneFromPnl(cell.total_pnl, cell.n_closed);
  return (
    <Link
      href={`/forwardtests/${encodeURIComponent(cell.strategy_id)}?env=${env}`}
      className={`block rounded-md border ${tone.border} ${tone.bg} px-2.5 py-2 transition hover:scale-[1.02] hover:shadow-md`}
    >
      <div className={`text-sm font-semibold tabular ${pnlClass(cell.total_pnl)}`}>
        {fmtMoney(cell.total_pnl)}
      </div>
      <div className="mt-1 flex items-center justify-between gap-2 text-[10px] text-muted-foreground">
        <span>{cell.win_rate != null ? `WR ${fmtPct(cell.win_rate)}` : "no closed"}</span>
        <span className="tabular">
          {cell.n_open}o · {cell.n_closed}c
        </span>
      </div>
    </Link>
  );
}

function EmptyCell() {
  return <div className="flex h-[60px] items-center justify-center rounded-md border border-dashed border-border/40 text-[10px] text-muted-foreground/60">—</div>;
}

function toneFromPnl(pnl: number, nClosed: number) {
  if (nClosed === 0 && pnl === 0) {
    return { bg: "bg-card/20", border: "border-border/40" };
  }
  if (pnl > 0) {
    return { bg: "bg-[var(--gain)]/10", border: "border-[var(--gain)]/30" };
  }
  if (pnl < 0) {
    return { bg: "bg-[var(--loss)]/10", border: "border-[var(--loss)]/30" };
  }
  return { bg: "bg-card/30", border: "border-border/40" };
}

function Section({ children }: { children: React.ReactNode }) {
  return (
    <section className="rounded-2xl border border-border/60 bg-gradient-to-b from-card/70 to-card/35 p-5 shadow-2xl shadow-black/10">
      <div className="mb-4 flex items-center gap-2">
        <span className="text-primary"><Grid3x3 className="h-4 w-4" /></span>
        <h3 className="text-sm font-semibold tracking-tight">Performance matrix</h3>
        <span className="ml-2 text-[11px] text-muted-foreground">family × structure × ticker</span>
      </div>
      {children}
    </section>
  );
}

function Empty({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded-xl border border-dashed border-border/50 bg-card/20 p-8 text-center">
      <h4 className="text-sm font-semibold">{title}</h4>
      <p className="mx-auto mt-2 max-w-xl text-[12px] text-muted-foreground">{body}</p>
    </div>
  );
}
