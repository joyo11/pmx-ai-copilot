import { TopBar } from "@/components/top-bar";
import { EmptyState } from "@/components/empty-state";
import { FileText } from "lucide-react";

export default function ReportsPage() {
  return (
    <>
      <TopBar title="Reports" />
      <main className="flex-1 p-6">
        <EmptyState
          Icon={FileText}
          title="No reports yet"
          description="Executive, weekly, and risk-only report templates ship in M2."
        />
      </main>
    </>
  );
}
