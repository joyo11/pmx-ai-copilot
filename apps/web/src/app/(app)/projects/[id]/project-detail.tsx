"use client";

import * as React from "react";
import { useAuth } from "@clerk/nextjs";
import { Activity, AlertTriangle, FileText, MessageSquare } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import {
  getProject,
  listDocuments,
  ApiError,
  type Project,
  type ProjectDocument,
} from "@/lib/api";
import { DocumentsPanel } from "./documents-panel";
import { ChatPanel } from "./chat-panel";

type Tab = "overview" | "documents" | "chat";

const TABS: { key: Tab; label: string; Icon: React.ComponentType<{ className?: string }> }[] = [
  { key: "overview", label: "Overview", Icon: Activity },
  { key: "documents", label: "Documents", Icon: FileText },
  { key: "chat", label: "Chat", Icon: MessageSquare },
];

export function ProjectDetail({ projectId }: { projectId: string }) {
  const { getToken, isLoaded } = useAuth();
  const [project, setProject] = React.useState<Project | null>(null);
  const [documents, setDocuments] = React.useState<ProjectDocument[]>([]);
  const [error, setError] = React.useState<string | null>(null);
  const [tab, setTab] = React.useState<Tab>("overview");

  const refresh = React.useCallback(async () => {
    setError(null);
    try {
      const token = await getToken();
      const [p, docs] = await Promise.all([
        getProject(projectId, { token }),
        listDocuments(projectId, { token }),
      ]);
      setProject(p);
      setDocuments(docs);
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? `API ${err.status}: ${err.body ?? err.message}`
          : err instanceof Error
            ? err.message
            : "Failed to load project";
      setError(msg);
    }
  }, [getToken, projectId]);

  React.useEffect(() => {
    if (isLoaded) void refresh();
  }, [isLoaded, refresh]);

  const onDocumentsChanged = React.useCallback(async () => {
    try {
      const token = await getToken();
      const docs = await listDocuments(projectId, { token });
      setDocuments(docs);
    } catch {
      // silent — the panel surfaces its own errors
    }
  }, [getToken, projectId]);

  if (!isLoaded || (!project && !error)) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-24 rounded-xl" />
        <Skeleton className="h-64 rounded-xl" />
      </div>
    );
  }

  if (error && !project) {
    return (
      <div className="flex items-start gap-3 rounded-lg border border-destructive/40 bg-destructive/10 p-4 text-sm">
        <AlertTriangle className="mt-0.5 size-4 shrink-0 text-destructive" />
        <div className="flex-1">
          <p className="font-medium text-destructive">Could not load project</p>
          <p className="text-muted-foreground">{error}</p>
        </div>
        <Button size="sm" variant="outline" onClick={() => void refresh()}>
          Retry
        </Button>
      </div>
    );
  }

  if (!project) return null;

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="space-y-2">
              <CardTitle className="text-2xl">{project.name}</CardTitle>
              <CardDescription className="flex flex-wrap items-center gap-3">
                {project.client ? <span>{project.client}</span> : null}
                {project.sector ? (
                  <Badge variant="secondary" className="capitalize">
                    {project.sector}
                  </Badge>
                ) : null}
                <span>·</span>
                <span>
                  {documents.length} document{documents.length === 1 ? "" : "s"}
                </span>
              </CardDescription>
            </div>
            <div className="text-right">
              <p className="text-xs uppercase tracking-wide text-muted-foreground">
                Health score
              </p>
              <p className="text-3xl font-semibold tabular-nums">
                {project.health_score ?? "—"}
              </p>
            </div>
          </div>
        </CardHeader>
      </Card>

      <div className="flex gap-1 border-b">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={cn(
              "-mb-px inline-flex items-center gap-2 border-b-2 px-3 py-2 text-sm font-medium transition-colors",
              tab === t.key
                ? "border-primary text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground"
            )}
          >
            <t.Icon className="size-4" />
            {t.label}
          </button>
        ))}
      </div>

      {tab === "overview" ? (
        <OverviewPanel project={project} documentCount={documents.length} />
      ) : null}
      {tab === "documents" ? (
        <DocumentsPanel
          projectId={projectId}
          documents={documents}
          onChanged={onDocumentsChanged}
        />
      ) : null}
      {tab === "chat" ? <ChatPanel projectId={projectId} /> : null}
    </div>
  );
}

function OverviewPanel({
  project,
  documentCount,
}: {
  project: Project;
  documentCount: number;
}) {
  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
      <StatCard label="Documents" value={String(documentCount)} />
      <StatCard label="Health" value={project.health_score?.toString() ?? "—"} />
      <StatCard label="Status" value={project.status} />
      <StatCard
        label="Sector"
        value={project.sector ?? "—"}
        className="capitalize"
      />
    </div>
  );
}

function StatCard({
  label,
  value,
  className,
}: {
  label: string;
  value: string;
  className?: string;
}) {
  return (
    <Card>
      <CardHeader>
        <CardDescription>{label}</CardDescription>
        <CardTitle
          className={cn("text-2xl font-semibold tabular-nums", className)}
        >
          {value}
        </CardTitle>
      </CardHeader>
    </Card>
  );
}
