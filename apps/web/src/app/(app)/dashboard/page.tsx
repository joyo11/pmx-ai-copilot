import { TopBar } from "@/components/top-bar";
import { DashboardView } from "./dashboard-view";

export default function DashboardPage() {
  return (
    <>
      <TopBar title="Dashboard" />
      <main className="flex-1 space-y-6 p-6">
        <DashboardView />
      </main>
    </>
  );
}
