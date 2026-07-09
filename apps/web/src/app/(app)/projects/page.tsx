import { TopBar } from "@/components/top-bar";
import { EmptyState } from "@/components/empty-state";
import { FolderKanban } from "lucide-react";

export default function ProjectsPage() {
  return (
    <>
      <TopBar title="Projects" />
      <main className="flex-1 p-6">
        <EmptyState
          Icon={FolderKanban}
          title="No projects yet"
          description="Create your first project to start uploading schedules, budgets, and RFIs. PMX AI will detect risks the moment your first document is processed."
          actionLabel="Create project"
        />
      </main>
    </>
  );
}
