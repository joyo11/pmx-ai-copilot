"use client";

import * as React from "react";
import Link from "next/link";
import { useAuth } from "@clerk/nextjs";
import { FolderKanban, Plus, AlertTriangle } from "lucide-react";

import { EmptyState } from "@/components/empty-state";
import { NewProjectDialog } from "@/components/new-project-dialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { listProjects, ApiError, type Project } from "@/lib/api";

export function ProjectsView() {
  const { getToken, isLoaded } = useAuth();
  const [projects, setProjects] = React.useState<Project[] | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [dialogOpen, setDialogOpen] = React.useState(false);

  const load = React.useCallback(async () => {
    setError(null);
    try {
      const token = await getToken();
      const rows = await listProjects({ token });
      setProjects(rows);
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? `API ${err.status}: ${err.body ?? err.message}`
          : err instanceof Error
            ? err.message
            : "Failed to load projects";
      setError(msg);
      setProjects([]);
    }
  }, [getToken]);

  React.useEffect(() => {
    if (isLoaded) void load();
  }, [isLoaded, load]);

  if (!isLoaded || projects === null) {
    return (
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-32 rounded-xl" />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <>
        <div className="mb-4 flex items-start gap-3 rounded-lg border border-destructive/40 bg-destructive/10 p-4 text-sm">
          <AlertTriangle className="mt-0.5 size-4 shrink-0 text-destructive" />
          <div className="flex-1">
            <p className="font-medium text-destructive">
              Could not load projects
            </p>
            <p className="text-muted-foreground">{error}</p>
          </div>
          <Button size="sm" variant="outline" onClick={() => void load()}>
            Retry
          </Button>
        </div>
        <EmptyState
          Icon={FolderKanban}
          title="No projects yet"
          description="Create your first project to start uploading schedules, budgets, and RFIs."
          actionLabel="Create project"
          onAction={() => setDialogOpen(true)}
        />
        <NewProjectDialog open={dialogOpen} onOpenChange={setDialogOpen} />
      </>
    );
  }

  if (projects.length === 0) {
    return (
      <>
        <EmptyState
          Icon={FolderKanban}
          title="No projects yet"
          description="Create your first project to start uploading schedules, budgets, and RFIs. PMX AI will detect risks the moment your first document is processed."
          actionLabel="Create project"
          onAction={() => setDialogOpen(true)}
        />
        <NewProjectDialog open={dialogOpen} onOpenChange={setDialogOpen} />
      </>
    );
  }

  return (
    <>
      <div className="mb-4 flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          {projects.length} project{projects.length === 1 ? "" : "s"}
        </p>
        <Button onClick={() => setDialogOpen(true)} size="sm">
          <Plus className="size-4" />
          New project
        </Button>
      </div>
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {projects.map((p) => (
          <ProjectCard key={p.id} project={p} />
        ))}
      </div>
      <NewProjectDialog open={dialogOpen} onOpenChange={setDialogOpen} />
    </>
  );
}

function ProjectCard({ project }: { project: Project }) {
  return (
    <Link
      href={`/projects/${project.id}`}
      className="block outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:rounded-xl"
    >
      <Card className="h-full transition-colors hover:bg-accent/40">
        <CardHeader>
          <CardTitle className="text-base">{project.name}</CardTitle>
          {project.client ? (
            <p className="text-xs text-muted-foreground">
              {project.client}
            </p>
          ) : null}
        </CardHeader>
        <CardContent className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
          <div className="flex items-center gap-2">
            {project.sector ? (
              <Badge variant="secondary" className="capitalize">
                {project.sector}
              </Badge>
            ) : null}
            <span>{project.document_count ?? 0} docs</span>
          </div>
          <span className="tabular-nums">
            Health {project.health_score ?? "—"}
          </span>
        </CardContent>
      </Card>
    </Link>
  );
}
