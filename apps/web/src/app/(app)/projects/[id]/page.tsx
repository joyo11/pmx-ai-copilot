import { TopBar } from "@/components/top-bar";
import { ProjectDetail } from "./project-detail";

// Next 15+ makes `params` a Promise on server components.
export default async function ProjectDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <>
      <TopBar title="Project" />
      <main className="flex-1 p-6">
        <ProjectDetail projectId={id} />
      </main>
    </>
  );
}
