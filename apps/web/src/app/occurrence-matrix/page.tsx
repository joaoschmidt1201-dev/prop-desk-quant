import { AppShell } from "@/components/layout/app-shell";
import { OccurrenceMatrixDashboard } from "@/components/occurrence-matrix/matrix-heatmap";
import { api, type OccurrenceMatrixPayload } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function OccurrenceMatrixPage() {
  let initialData: OccurrenceMatrixPayload | null = null;

  try {
    initialData = await api.occurrenceMatrix();
  } catch {
    initialData = null;
  }

  return (
    <AppShell>
      <OccurrenceMatrixDashboard initialData={initialData} />
    </AppShell>
  );
}
