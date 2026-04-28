import { AppShell } from "@/components/layout/app-shell";
import { BacktestsOverview } from "@/components/backtests/backtests-overview";

export default function BacktestsPage() {
  return (
    <AppShell>
      <BacktestsOverview />
    </AppShell>
  );
}
