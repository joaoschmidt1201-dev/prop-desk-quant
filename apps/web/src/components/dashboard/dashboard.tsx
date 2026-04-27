"use client";

import { useState } from "react";
import type { Filter } from "@/lib/api";
import { ChatPanel } from "./chat-panel";
import { DashboardHeader } from "./header";
import { KpiGrid } from "./kpi-grid";
import { MonthFilter } from "./month-filter";
import { TradesTable } from "./trades-table";

export function Dashboard() {
  const [filter, setFilter] = useState<Filter>({ months: [], env: null });

  return (
    <div className="min-h-screen flex flex-col">
      <DashboardHeader />
      <main className="mx-auto w-full max-w-[1600px] flex-1 px-6 py-6">
        <div className="mb-6">
          <MonthFilter
            selectedMonths={filter.months}
            onChange={(months) => setFilter((f) => ({ ...f, months }))}
          />
        </div>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
          <div className="space-y-6 lg:col-span-8">
            <KpiGrid filter={filter} />
            <TradesTable filter={filter} />
          </div>
          <div className="lg:col-span-4">
            <div className="sticky top-24">
              <ChatPanel filter={filter} />
            </div>
          </div>
        </div>
      </main>
      <footer className="mx-auto w-full max-w-[1600px] px-6 pb-6 pt-4 text-center text-[11px] text-muted-foreground">
        CZ Dashboard · Proprietary trading desk · Data via Google Sheets · No execution
      </footer>
    </div>
  );
}
