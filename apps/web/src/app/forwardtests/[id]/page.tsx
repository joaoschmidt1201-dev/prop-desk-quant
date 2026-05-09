import { AppShell } from "@/components/layout/app-shell";
import { ForwardtestDetail } from "@/components/forwardtests/forwardtest-detail";
import type { ForwardtestEnv } from "@/lib/api";

type SearchParams = Promise<{ env?: string }>;

export default async function ForwardtestDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: SearchParams;
}) {
  const { id } = await params;
  const sp = await searchParams;
  const env: ForwardtestEnv = sp.env === "JS_Forward" ? "JS_Forward" : "CZ_Forward";
  return (
    <AppShell>
      <ForwardtestDetail strategyId={id} env={env} />
    </AppShell>
  );
}
