import { AppShell } from "@/components/layout/app-shell";
import { GexDashboard } from "@/components/gex/gex-dashboard";
import { api, type GexExpirations, type GexProfile } from "@/lib/api";

export const dynamic = "force-dynamic";

// The desk thinks in indices; the backend reads the ETF proxy chain (Yahoo lacks
// index option chains) and flags `proxy` so the UI can say so.
const DEFAULT_UNDERLYING = "SPX";

export default async function GexPage() {
  let initialExpirations: GexExpirations | null = null;
  let initialProfile: GexProfile | null = null;

  try {
    [initialExpirations, initialProfile] = await Promise.all([
      api.gexExpirations(DEFAULT_UNDERLYING),
      api.gexProfile(DEFAULT_UNDERLYING),
    ]);
  } catch {
    initialExpirations = null;
    initialProfile = null;
  }

  return (
    <AppShell>
      <GexDashboard
        underlying={DEFAULT_UNDERLYING}
        initialExpirations={initialExpirations}
        initialProfile={initialProfile}
      />
    </AppShell>
  );
}
