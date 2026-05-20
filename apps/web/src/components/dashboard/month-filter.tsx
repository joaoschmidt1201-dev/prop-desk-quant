"use client";

import { useQuery } from "@tanstack/react-query";
import { Check } from "lucide-react";
import { useEffect, useMemo } from "react";
import { api } from "@/lib/api";
import { DASHBOARD_REFETCH_INTERVAL_MS } from "@/lib/refresh";

type DeskUser = "CZ" | "JS";

type Props = {
  selectedUser: DeskUser;
  selectedMonths: string[];
  live: boolean;
  onUserChange: (user: DeskUser) => void;
  onChange: (months: string[]) => void;
  onLiveChange: (live: boolean) => void;
};

function isJsMonth(sheet: string): boolean {
  return sheet.trim().toUpperCase().startsWith("JS ");
}

export function MonthFilter({
  selectedUser,
  selectedMonths,
  live,
  onUserChange,
  onChange,
  onLiveChange,
}: Props) {
  const { data } = useQuery({
    queryKey: ["months"],
    queryFn: () => api.months(),
    refetchInterval: DASHBOARD_REFETCH_INTERVAL_MS,
    refetchIntervalInBackground: true,
  });
  const months = data?.months ?? [];

  const visibleMonths = useMemo(
    () => months.filter((month) => (selectedUser === "JS" ? isJsMonth(month.sheet) : !isJsMonth(month.sheet))),
    [months, selectedUser],
  );
  const visibleSheets = useMemo(() => visibleMonths.map((month) => month.sheet), [visibleMonths]);
  const visibleSheetSet = useMemo(() => new Set(visibleSheets), [visibleSheets]);
  const selectedInScope = selectedMonths.filter((sheet) => visibleSheetSet.has(sheet));
  const allVisibleSelected =
    visibleSheets.length > 0 &&
    selectedInScope.length === visibleSheets.length &&
    visibleSheets.every((sheet) => selectedMonths.includes(sheet));

  useEffect(() => {
    if (!months.length) return;

    if (!visibleSheets.length) {
      if (selectedMonths.length) onChange([]);
      return;
    }

    const hasOutOfScope = selectedMonths.some((sheet) => !visibleSheetSet.has(sheet));
    if (!selectedInScope.length || hasOutOfScope) {
      onChange(visibleSheets);
    }
  }, [months.length, onChange, selectedInScope.length, selectedMonths, visibleSheetSet, visibleSheets]);

  function toggle(sheet: string) {
    onLiveChange(false); // choosing a period exits the live view
    if (selectedMonths.includes(sheet)) {
      const next = selectedMonths.filter((month) => month !== sheet);
      onChange(next.length ? next : visibleSheets);
    } else {
      onChange([...selectedInScope, sheet]);
    }
  }

  return (
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div className="flex min-w-0 flex-wrap items-center gap-1.5">
        <span className="mr-1 text-[10px] uppercase tracking-[0.22em] text-muted-foreground/70">Period</span>
        <button
          onClick={() => onLiveChange(true)}
          className={`flex items-center gap-1.5 rounded-md px-3 py-1 text-[11px] font-semibold transition ${
            live
              ? "bg-[var(--gain)]/15 text-[var(--gain)] ring-1 ring-[var(--gain)]/40"
              : "text-muted-foreground hover:bg-card/50 hover:text-foreground"
          }`}
          title="Open positions only, across all months"
        >
          <span className={`h-1.5 w-1.5 rounded-full ${live ? "bg-[var(--gain)] animate-pulse" : "bg-muted-foreground/60"}`} />
          Live
        </button>
        <span className="mx-0.5 h-4 w-px bg-border/50" aria-hidden />
        <button
          onClick={() => {
            onLiveChange(false);
            onChange(visibleSheets);
          }}
          className={`rounded-md px-3 py-1 text-[11px] font-medium transition ${
            !live && allVisibleSelected
              ? "bg-primary/15 text-primary ring-1 ring-primary/40"
              : "text-muted-foreground hover:bg-card/50 hover:text-foreground"
          }`}
        >
          All
        </button>
        {visibleMonths.map((month) => {
          const active = !live && selectedMonths.includes(month.sheet);
          return (
            <button
              key={month.sheet}
              onClick={() => toggle(month.sheet)}
              className={`flex items-center gap-1.5 rounded-md px-3 py-1 text-[11px] font-medium transition ${
                live ? "opacity-50" : ""
              } ${
                active
                  ? "bg-primary/15 text-primary ring-1 ring-primary/40"
                  : "text-muted-foreground hover:bg-card/50 hover:text-foreground"
              }`}
            >
              {active && <Check className="h-3 w-3" />}
              <span>{month.label}</span>
              <span className="tabular text-[10px] opacity-60">{month.n_trades}</span>
              {month.active && <span className="h-1 w-1 rounded-full bg-[var(--gain)]" aria-label="active" />}
            </button>
          );
        })}
        {!visibleMonths.length && (
          <span className="px-2 py-1 text-[11px] text-muted-foreground">No periods</span>
        )}
      </div>

      <div className="flex items-center gap-2">
        <span className="text-[10px] uppercase tracking-[0.22em] text-muted-foreground/70">User</span>
        <div className="inline-flex overflow-hidden rounded-md border border-border/50 bg-card/20 p-0.5">
          {(["CZ", "JS"] as const).map((user) => {
            const active = selectedUser === user;
            return (
              <button
                key={user}
                onClick={() => onUserChange(user)}
                className={`min-w-12 rounded px-3 py-1 text-[11px] font-semibold transition ${
                  active
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:bg-card/60 hover:text-foreground"
                }`}
              >
                {user}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
