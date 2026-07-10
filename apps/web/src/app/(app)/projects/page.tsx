import { TopBar } from "@/components/top-bar";
import { ProjectsView } from "./projects-view";

export default function ProjectsPage() {
  return (
    <>
      <TopBar title="Projects" />
      <main className="flex-1 p-6">
        <ProjectsView />
      </main>
    </>
  );
}
