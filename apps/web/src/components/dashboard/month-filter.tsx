"use client";

import { useQuery } from "@tanstack/react-query";
import { Check } from "lucide-react";
import { api } from "@/lib/api";

type Props = {
  selectedMonths: string[];
  onChange: (months: string[]) => void;
};

export function MonthFilter({ selectedMonths, onChange }: Props) {
  const { data } = useQuery({ queryKey: ["months"], queryFn: () => api.months() });
  const months = data?.months ?? [];

  function toggle(sheet: string) {
    if (selectedMonths.includes(sheet)) {
      onChange(selectedMonths.filter((m) => m !== sheet));
    } else {
      onChange([...selectedMonths, sheet]);
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-xs uppercase tracking-wider text-muted-foreground">Filter</span>
      <button
        onClick={() => onChange([])}
        className={`rounded-md border px-3 py-1.5 text-xs font-medium transition ${
          selectedMonths.length === 0
            ? "border-primary/60 bg-primary/15 text-primary"
            : "border-border/60 bg-card/40 text-muted-foreground hover:bg-card hover:text-foreground"
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
            className={`flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium transition ${
              active
                ? "border-primary/60 bg-primary/15 text-primary"
                : "border-border/60 bg-card/40 text-muted-foreground hover:bg-card hover:text-foreground"
            }`}
          >
            {active && <Check className="h-3 w-3" />}
            <span>{m.label}</span>
            <span className="tabular text-[10px] opacity-60">·{m.n_trades}</span>
            {m.active && <span className="h-1.5 w-1.5 rounded-full bg-[var(--gain)]" aria-label="active" />}
          </button>
        );
      })}
    </div>
  );
}
