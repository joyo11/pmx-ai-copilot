import { TopBar } from "@/components/top-bar";
import { EmptyState } from "@/components/empty-state";
import { Settings } from "lucide-react";

export default function SettingsPage() {
  return (
    <>
      <TopBar title="Settings" />
      <main className="flex-1 p-6">
        <EmptyState
          Icon={Settings}
          title="Settings coming soon"
          description="Organization, team, integrations, and API keys land in M0.4 when auth wires up."
        />
      </main>
    </>
  );
}
