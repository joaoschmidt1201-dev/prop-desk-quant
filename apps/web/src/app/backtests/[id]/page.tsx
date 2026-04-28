import { AppShell } from "@/components/layout/app-shell";
import { BacktestDetail } from "@/components/backtests/backtest-detail";

export default async function BacktestDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <AppShell>
      <BacktestDetail id={id} />
    </AppShell>
  );
}
