"use client";

import { useState } from "react";
import type { Filter } from "@/lib/api";
import { AnalyticsPanel } from "./analytics-panel";
import { ChatPanel } from "./chat-panel";
import { DashboardHeader } from "./header";
import { KpiGrid } from "./kpi-grid";
import { MonthFilter } from "./month-filter";
import { TradesTable } from "./trades-table";

export function Dashboard() {
  const [filter, setFilter] = useState<Filter>({ months: [], env: null });

  return (
    <div className="flex min-h-screen flex-col">
      <DashboardHeader />
      <main className="mx-auto w-full max-w-[1600px] flex-1 px-8 py-8">
        <div className="mb-7">
          <MonthFilter
            selectedMonths={filter.months}
            onChange={(months) => setFilter((f) => ({ ...f, months }))}
          />
        </div>

        <div className="grid grid-cols-1 gap-7 lg:grid-cols-12">
          <div className="space-y-7 lg:col-span-8">
            <KpiGrid filter={filter} />
            <TradesTable filter={filter} />
          </div>
          <div className="lg:col-span-4">
            <div className="sticky top-24">
              <ChatPanel filter={filter} />
            </div>
          </div>
        </div>

        <div className="mt-7">
          <AnalyticsPanel filter={filter} />
        </div>
      </main>
      <footer className="mx-auto w-full max-w-[1600px] px-8 pb-8 pt-6 text-center text-[10px] text-muted-foreground/60">
        ST Quant Desk · Proprietary trading · Data via Google Sheets · No execution
      </footer>
    </div>
  );
}
