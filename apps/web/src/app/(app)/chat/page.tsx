import { TopBar } from "@/components/top-bar";
import { EmptyState } from "@/components/empty-state";
import { MessageSquare } from "lucide-react";

export default function ChatPage() {
  return (
    <>
      <TopBar title="Chat" />
      <main className="flex-1 p-6">
        <EmptyState
          Icon={MessageSquare}
          title="Ask PMX AI anything"
          description="Cross-project chat with citations. Ships in M1 alongside the risk engine."
        />
      </main>
    </>
  );
}
