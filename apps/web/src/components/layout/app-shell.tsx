"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Activity, BarChart3, FlaskConical, Grid3X3, LineChart, Radar, Sparkles } from "lucide-react";
import type { ReactNode } from "react";
import { api } from "@/lib/api";
import { fmtRelativeAge } from "@/lib/format";

type NavItem = {
  href: string;
  label: string;
  icon: ReactNode;
  match: (pathname: string) => boolean;
};

const NAV: NavItem[] = [
  {
    href: "/dashboard",
    label: "Dashboard",
    icon: <LineChart className="h-4 w-4" />,
    match: (p) => p === "/" || p.startsWith("/dashboard"),
  },
  {
    href: "/backtests",
    label: "Backtests",
    icon: <FlaskConical className="h-4 w-4" />,
    match: (p) => p.startsWith("/backtests"),
  },
  {
    href: "/forwardtests",
    label: "Forwardtests",
    icon: <Radar className="h-4 w-4" />,
    match: (p) => p.startsWith("/forwardtests"),
  },
  {
    href: "/occurrence-matrix",
    label: "Occurrence Matrix",
    icon: <Grid3X3 className="h-4 w-4" />,
    match: (p) => p.startsWith("/occurrence-matrix"),
  },
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { data: health } = useQuery({
    queryKey: ["health"],
    queryFn: () => api.health(),
    refetchInterval: 60_000,
  });

  return (
    <div className="flex min-h-screen">
      <Sidebar pathname={pathname} healthAge={health?.snapshot_age_seconds} />
      <div className="ml-[240px] flex min-h-screen flex-1 flex-col">
        {children}
      </div>
    </div>
  );
}

function Sidebar({ pathname, healthAge }: { pathname: string; healthAge: number | null | undefined }) {
  return (
    <aside className="fixed left-0 top-0 z-40 flex h-screen w-[240px] flex-col border-r border-border/60 bg-[oklch(0.155_0.02_250_/_0.85)] backdrop-blur-xl">
      <div className="flex items-center gap-3 border-b border-border/40 px-5 py-5">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-primary/30 to-accent/30 ring-1 ring-primary/40">
          <Activity className="h-5 w-5 text-primary" />
        </div>
        <div className="leading-tight">
          <div className="text-[13px] font-semibold tracking-tight">ST Quant Desk</div>
          <div className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">Prop Trading</div>
        </div>
      </div>

      <nav className="flex-1 px-3 py-4">
        <div className="mb-2 px-2 text-[10px] font-medium uppercase tracking-[0.22em] text-muted-foreground/80">
          Workspace
        </div>
        <ul className="space-y-1">
          {NAV.map((item) => {
            const active = item.match(pathname);
            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  className={`group flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition ${
                    active
                      ? "bg-primary/15 text-primary ring-1 ring-primary/25"
                      : "text-muted-foreground hover:bg-card/40 hover:text-foreground"
                  }`}
                >
                  <span className={active ? "text-primary" : "text-muted-foreground/80 group-hover:text-foreground"}>
                    {item.icon}
                  </span>
                  <span>{item.label}</span>
                  {active && <span className="ml-auto h-1.5 w-1.5 rounded-full bg-primary" />}
                </Link>
              </li>
            );
          })}
        </ul>

        <div className="mt-8 mb-2 px-2 text-[10px] font-medium uppercase tracking-[0.22em] text-muted-foreground/80">
          Coming soon
        </div>
        <ul className="space-y-1">
          {["GEX Levels"].map((label) => (
            <li key={label}>
              <div className="flex cursor-not-allowed items-center gap-3 rounded-lg px-3 py-2 text-sm text-muted-foreground/40">
                <BarChart3 className="h-4 w-4" />
                {label}
              </div>
            </li>
          ))}
        </ul>
      </nav>

      <div className="border-t border-border/40 px-4 py-4">
        <div className="flex items-center gap-2 rounded-lg border border-border/60 bg-background/30 px-3 py-2">
          <span className="relative inline-flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full rounded-full bg-[var(--gain)] opacity-60 animate-ping" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-[var(--gain)]" />
          </span>
          <div className="flex flex-col leading-tight">
            <span className="text-[10px] uppercase tracking-wider text-muted-foreground">Snapshot</span>
            <span className="tabular text-[11px]">{fmtRelativeAge(healthAge)}</span>
          </div>
          <Sparkles className="ml-auto h-3.5 w-3.5 text-accent/70" />
        </div>
        <div className="mt-3 text-center text-[10px] text-muted-foreground/70">
          v0.2 · ST Quant Desk
        </div>
      </div>
    </aside>
  );
}
