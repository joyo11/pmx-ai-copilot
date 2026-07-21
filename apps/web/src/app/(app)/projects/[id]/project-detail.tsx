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

function healthBand(score: number | null): {
  label: string;
  color: string;
  soft: string;
} {
  const s = typeof score === "number" ? score : 100;
  if (s >= 75) return { label: "Healthy", color: "#35C97F", soft: "rgba(53,201,127,.15)" };
  if (s >= 50) return { label: "On watch", color: "#F2B233", soft: "rgba(242,178,51,.15)" };
  if (s >= 30) return { label: "At risk", color: "#F5893D", soft: "rgba(245,137,61,.15)" };
  return { label: "Critical", color: "#F65563", soft: "rgba(246,85,99,.16)" };
}

function weeksBetween(
  plannedIso?: string | null,
  forecastIso?: string | null
): number | null {
  if (!plannedIso || !forecastIso) return null;
  const p = new Date(plannedIso).getTime();
  const f = new Date(forecastIso).getTime();
  if (Number.isNaN(p) || Number.isNaN(f)) return null;
  return Math.round((f - p) / (1000 * 60 * 60 * 24 * 7));
}

function compactUSD(cents?: number | null): string | null {
  if (typeof cents !== "number") return null;
  const dollars = cents / 100;
  if (dollars >= 1e6) return `$${(dollars / 1e6).toFixed(1)}M`;
  if (dollars >= 1e3) return `$${(dollars / 1e3).toFixed(0)}K`;
  return `$${dollars.toFixed(0)}`;
}

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
  const band = healthBand(headerScore);
  const scheduleWeeks = weeksBetween(
    project.planned_end_date,
    project.forecast_end_date
  );
  const contract = compactUSD(project.budget_total_cents);

  return (
    <div className="space-y-6">
      {/* Rich project header (Claude Design layout): band + stat row + ask CTA */}
      <div className="rounded-2xl border bg-card p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="mb-2 flex flex-wrap items-center gap-2.5">
              <span
                className="rounded-full px-2.5 py-1 text-xs font-bold"
                style={{ background: band.soft, color: band.color }}
              >
                {band.label}
                {typeof headerScore === "number"
                  ? ` · Health ${Math.round(headerScore)}`
                  : ""}
              </span>
              <span className="text-[13px] capitalize text-muted-foreground">
                {project.sector}
                {project.client ? ` · ${project.client}` : ""}
              </span>
            </div>
            <h1 className="font-display text-[26px] font-bold tracking-tight">
              {project.name}
            </h1>
            <div className="mt-2.5 flex flex-wrap gap-x-5 gap-y-1 text-[13.5px] text-muted-foreground">
              {contract ? (
                <span>
                  <b className="tabular-nums text-foreground">{contract}</b>{" "}
                  contract
                </span>
              ) : null}
              {scheduleWeeks !== null && scheduleWeeks !== 0 ? (
                <span>
                  <b
                    className="tabular-nums"
                    style={{ color: scheduleWeeks > 0 ? "#F65563" : "#35C97F" }}
                  >
                    {scheduleWeeks > 0 ? "−" : "+"}
                    {Math.abs(scheduleWeeks)} wk
                  </b>{" "}
                  schedule
                </span>
              ) : null}
              <span>
                <b className="tabular-nums text-foreground">
                  {documents.length}
                </b>{" "}
                document{documents.length === 1 ? "" : "s"}
              </span>
            </div>
          </div>
          <Button onClick={() => setTab("chat")} className="gap-2">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
              <path
                d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.4A8 8 0 1 1 21 12Z"
                stroke="currentColor"
                strokeWidth="1.7"
                strokeLinejoin="round"
              />
            </svg>
            Ask about this project
          </Button>
        </div>
      </div>

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
  // Contract value (GMP) formatted compact, e.g. $48.0M.
  const contract = compactUSD(project.budget_total_cents);

  // Schedule variance: forecast later than planned = slipping (red).
  const scheduleWeeks = weeksBetween(
    project.planned_end_date,
    project.forecast_end_date
  );

  // Budget variance: spent as a share of the total contract value.
  const total = project.budget_total_cents;
  const spent = project.budget_spent_cents;
  const budgetPct =
    typeof total === "number" && total > 0 && typeof spent === "number"
      ? Math.round((spent / total) * 100)
      : null;

  return (
    <div className="space-y-5">
      {/* Big health gauge + contributing factors (self-contained card). */}
      <HealthGauge
        snapshot={health}
        loading={healthLoading}
        error={healthError}
        onRecompute={onRecomputeHealth}
        recomputing={recomputing}
        hasDocuments={documentCount > 0}
      />

      {/* Quick-stat tiles below the gauge. */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <QuickStat
          label="Contract value"
          value={contract ?? "—"}
          valueColor="#E7EEF7"
          sub="GMP"
        />
        <QuickStat
          label="Schedule variance"
          value={
            scheduleWeeks === null || scheduleWeeks === 0
              ? "on track"
              : `${scheduleWeeks > 0 ? "−" : "+"}${Math.abs(scheduleWeeks)} wk`
          }
          valueColor={
            scheduleWeeks && scheduleWeeks > 0
              ? "#F65563"
              : scheduleWeeks && scheduleWeeks < 0
                ? "#35C97F"
                : "#35C97F"
          }
          sub={
            scheduleWeeks && scheduleWeeks > 0
              ? "behind plan"
              : scheduleWeeks && scheduleWeeks < 0
                ? "ahead of plan"
                : "vs. baseline"
          }
        />
        <QuickStat
          label="Budget variance"
          value={budgetPct === null ? "—" : `${budgetPct}%`}
          valueColor={
            budgetPct === null
              ? "#E7EEF7"
              : budgetPct >= 100
                ? "#F65563"
                : budgetPct >= 80
                  ? "#F5893D"
                  : "#35C97F"
          }
          sub={budgetPct === null ? "no data" : "of GMP spent"}
          className="col-span-2 sm:col-span-1"
        />
      </div>
    </div>
  );
}

function QuickStat({
  label,
  value,
  valueColor,
  sub,
  className,
}: {
  label: string;
  value: string;
  valueColor: string;
  sub: string;
  className?: string;
}) {
  return (
    <div className={cn("rounded-2xl border bg-card p-4", className)}>
      <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      <p
        className="mt-1.5 font-display text-2xl font-bold tabular-nums leading-none"
        style={{ color: valueColor }}
      >
        {value}
      </p>
      <p className="mt-1 text-xs text-muted-foreground">{sub}</p>
    </div>
  );
}
