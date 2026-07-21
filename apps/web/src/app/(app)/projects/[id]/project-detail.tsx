"use client";

import * as React from "react";
import { useAuth } from "@clerk/nextjs";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import {
  Activity,
  AlertTriangle,
  FileText,
  MessageSquare,
  ShieldAlert,
  Sparkles,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import {
  getHealth,
  getProject,
  listDocuments,
  listRisks,
  recomputeHealth,
  ApiError,
  type HealthSnapshot,
  type Project,
  type ProjectDocument,
} from "@/lib/api";
import { HealthGauge } from "@/components/health-gauge";
import { DocumentsPanel } from "./documents-panel";
import { ChatPanel } from "./chat-panel";
import { RisksPanel } from "./risks-panel";
import { MeetingsPanel } from "./meetings-panel";

type Tab = "overview" | "risks" | "documents" | "meetings" | "chat";

const TABS: {
  key: Tab;
  label: string;
  Icon: React.ComponentType<{ className?: string }>;
}[] = [
  { key: "overview", label: "Overview", Icon: Activity },
  { key: "risks", label: "Risks", Icon: ShieldAlert },
  { key: "documents", label: "Documents", Icon: FileText },
  { key: "meetings", label: "Meetings", Icon: Sparkles },
  { key: "chat", label: "Chat", Icon: MessageSquare },
];

export function ProjectDetail({ projectId }: { projectId: string }) {
  const { getToken, isLoaded } = useAuth();
  const [project, setProject] = React.useState<Project | null>(null);
  const [documents, setDocuments] = React.useState<ProjectDocument[]>([]);
  const [health, setHealth] = React.useState<HealthSnapshot | null>(null);
  const [healthError, setHealthError] = React.useState<string | null>(null);
  const [healthLoading, setHealthLoading] = React.useState(true);
  const [recomputing, setRecomputing] = React.useState(false);
  const [criticalOpen, setCriticalOpen] = React.useState(0);
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

  const refreshHealth = React.useCallback(async () => {
    setHealthError(null);
    setHealthLoading(true);
    try {
      const token = await getToken();
      const snap = await getHealth(projectId, { token });
      setHealth(snap);
    } catch (err) {
      // A missing snapshot isn't necessarily an error worth surfacing
      // — the gauge falls back to an empty state and offers "Compute".
      if (err instanceof ApiError && err.status === 404) {
        setHealth(null);
      } else {
        const msg =
          err instanceof ApiError
            ? `API ${err.status}: ${err.body ?? err.message}`
            : err instanceof Error
              ? err.message
              : "Failed to load health";
        setHealthError(msg);
      }
    } finally {
      setHealthLoading(false);
    }
  }, [getToken, projectId]);

  const refreshCriticalCount = React.useCallback(async () => {
    try {
      const token = await getToken();
      const rows = await listRisks(
        projectId,
        { severity_gte: 4, status: "open" },
        { token }
      );
      setCriticalOpen(rows.length);
    } catch {
      // Non-fatal — the badge is a nice-to-have.
    }
  }, [getToken, projectId]);

  React.useEffect(() => {
    if (!isLoaded) return;
    void refresh();
    void refreshHealth();
    void refreshCriticalCount();
  }, [isLoaded, refresh, refreshHealth, refreshCriticalCount]);

  const onDocumentsChanged = React.useCallback(async () => {
    try {
      const token = await getToken();
      const docs = await listDocuments(projectId, { token });
      setDocuments(docs);
    } catch {
      // silent — the panel surfaces its own errors
    }
  }, [getToken, projectId]);

  const onRecomputeHealth = React.useCallback(async () => {
    if (recomputing) return;
    setRecomputing(true);
    try {
      const token = await getToken();
      const snap = await recomputeHealth(projectId, { token });
      setHealth(snap);
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? `API ${err.status}: ${err.body ?? err.message}`
          : err instanceof Error
            ? err.message
            : "Recompute failed";
      setHealthError(msg);
    } finally {
      setRecomputing(false);
    }
  }, [getToken, projectId, recomputing]);

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

  const headerScore = health?.score ?? project.health_score ?? null;

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
                {typeof headerScore === "number"
                  ? Math.round(headerScore)
                  : "—"}
              </p>
            </div>
          </div>
        </CardHeader>
      </Card>

      <div className="flex gap-1 overflow-x-auto border-b">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={cn(
              "-mb-px inline-flex min-h-11 shrink-0 items-center gap-2 border-b-2 px-3 py-2 text-sm font-medium transition-colors",
              tab === t.key
                ? "border-primary text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground"
            )}
          >
            <t.Icon className="size-4" />
            {t.label}
            {t.key === "risks" && criticalOpen > 0 ? (
              <Badge
                variant="destructive"
                className="ml-0.5 h-5 min-w-5 justify-center px-1.5 text-[10px] tabular-nums"
              >
                {criticalOpen}
              </Badge>
            ) : null}
          </button>
        ))}
      </div>

      <AnimatePresence mode="wait" initial={false}>
        <TabPanel key={tab}>
          {tab === "overview" ? (
            <OverviewPanel
              project={project}
              documentCount={documents.length}
              health={health}
              healthLoading={healthLoading}
              healthError={healthError}
              onRecomputeHealth={onRecomputeHealth}
              recomputing={recomputing}
            />
          ) : null}
          {tab === "risks" ? (
            <RisksPanel
              projectId={projectId}
              onCountsChange={setCriticalOpen}
            />
          ) : null}
          {tab === "documents" ? (
            <DocumentsPanel
              projectId={projectId}
              documents={documents}
              onChanged={onDocumentsChanged}
            />
          ) : null}
          {tab === "meetings" ? (
            <MeetingsPanel
              projectId={projectId}
              onSwitchToRisks={() => setTab("risks")}
            />
          ) : null}
          {tab === "chat" ? <ChatPanel projectId={projectId} /> : null}
        </TabPanel>
      </AnimatePresence>
    </div>
  );
}

function TabPanel({ children }: { children: React.ReactNode }) {
  const reduceMotion = useReducedMotion();
  return (
    <motion.div
      initial={reduceMotion ? { opacity: 1, x: 0 } : { opacity: 0, x: 12 }}
      animate={{ opacity: 1, x: 0 }}
      exit={reduceMotion ? { opacity: 1 } : { opacity: 0 }}
      transition={{ duration: reduceMotion ? 0 : 0.2, ease: "easeOut" }}
    >
      {children}
    </motion.div>
  );
}

function OverviewPanel({
  project,
  documentCount,
  health,
  healthLoading,
  healthError,
  onRecomputeHealth,
  recomputing,
}: {
  project: Project;
  documentCount: number;
  health: HealthSnapshot | null;
  healthLoading: boolean;
  healthError: string | null;
  onRecomputeHealth: () => void | Promise<void>;
  recomputing: boolean;
}) {
  return (
    <div className="space-y-4">
      <HealthGauge
        snapshot={health}
        loading={healthLoading}
        error={healthError}
        onRecompute={onRecomputeHealth}
        recomputing={recomputing}
        hasDocuments={documentCount > 0}
      />
      <div className="grid gap-4 md:grid-cols-3">
        <StatCard label="Documents" value={String(documentCount)} />
        <StatCard label="Status" value={project.status} />
        <StatCard
          label="Sector"
          value={project.sector ?? "—"}
          className="capitalize"
        />
      </div>
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
