import { AppShell } from "@/components/layout/app-shell";
import { ForwardtestDetail } from "@/components/forwardtests/forwardtest-detail";

export default async function ForwardtestDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <AppShell>
      <ForwardtestDetail strategyId={id} />
    </AppShell>
  );
}
