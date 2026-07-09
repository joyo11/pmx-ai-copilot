import { TopBar } from "@/components/top-bar";
import { EmptyState } from "@/components/empty-state";
import { Bell } from "lucide-react";

export default function NotificationsPage() {
  return (
    <>
      <TopBar title="Notifications" />
      <main className="flex-1 p-6">
        <EmptyState
          Icon={Bell}
          title="You're all caught up"
          description="Alerts land here when the risk engine detects a change or a threshold is crossed."
        />
      </main>
    </>
  );
}
