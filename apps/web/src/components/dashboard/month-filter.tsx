"use client";

import { useQuery } from "@tanstack/react-query";
import { Check } from "lucide-react";
import { useEffect, useRef } from "react";
import { api } from "@/lib/api";
import { DASHBOARD_REFETCH_INTERVAL_MS } from "@/lib/refresh";

type Props = {
  selectedMonths: string[];
  onChange: (months: string[]) => void;
};

export function MonthFilter({ selectedMonths, onChange }: Props) {
  const { data } = useQuery({
    queryKey: ["months"],
    queryFn: () => api.months(),
    refetchInterval: DASHBOARD_REFETCH_INTERVAL_MS,
    refetchIntervalInBackground: true,
  });
  const months = data?.months ?? [];
  const manualSelection = useRef(false);

  useEffect(() => {
    if (manualSelection.current || !months.length) return;
    const cristianoMonths = months.filter((m) => !m.sheet.toUpperCase().startsWith("JS")).map((m) => m.sheet);
    if (!cristianoMonths.length) return;
    if (
      selectedMonths.length === cristianoMonths.length &&
      cristianoMonths.every((sheet) => selectedMonths.includes(sheet))
    ) {
      return;
    }
    onChange(cristianoMonths);
  }, [months, onChange, selectedMonths]);

  function toggle(sheet: string) {
    manualSelection.current = true;
    if (selectedMonths.includes(sheet)) {
      onChange(selectedMonths.filter((m) => m !== sheet));
    } else {
      onChange([...selectedMonths, sheet]);
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="mr-1 text-[10px] uppercase tracking-[0.22em] text-muted-foreground/70">Period</span>
      <button
        onClick={() => {
          manualSelection.current = true;
          onChange([]);
        }}
        className={`rounded-full px-3 py-1 text-[11px] font-medium transition ${
          selectedMonths.length === 0
            ? "bg-primary/15 text-primary ring-1 ring-primary/40"
            : "text-muted-foreground hover:bg-card/50 hover:text-foreground"
        }`}
      >
        All
      </button>
      {months.map((m) => {
        const active = selectedMonths.includes(m.sheet);
        return (
          <button
            key={m.sheet}
            onClick={() => toggle(m.sheet)}
            className={`flex items-center gap-1.5 rounded-full px-3 py-1 text-[11px] font-medium transition ${
              active
                ? "bg-primary/15 text-primary ring-1 ring-primary/40"
                : "text-muted-foreground hover:bg-card/50 hover:text-foreground"
            }`}
          >
            {active && <Check className="h-3 w-3" />}
            <span>{m.label}</span>
            <span className="tabular text-[10px] opacity-60">{m.n_trades}</span>
            {m.active && <span className="h-1 w-1 rounded-full bg-[var(--gain)]" aria-label="active" />}
          </button>
        );
      })}
    </div>
  );
}
