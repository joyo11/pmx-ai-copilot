"use client";

import * as React from "react";
import Link from "next/link";
import { useAuth } from "@clerk/nextjs";
import { motion, useReducedMotion } from "motion/react";
import {
  Activity,
  AlertCircle,
  FileText,
  FolderKanban,
  AlertTriangle,
  Plus,
} from "lucide-react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { NewProjectDialog } from "@/components/new-project-dialog";
import { listProjects, listRisks, ApiError, type Project } from "@/lib/api";

export function DashboardView() {
  const { getToken, isLoaded } = useAuth();
  const [projects, setProjects] = React.useState<Project[] | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [dialogOpen, setDialogOpen] = React.useState(false);
  const [atRiskCount, setAtRiskCount] = React.useState<number | null>(null);

  React.useEffect(() => {
    if (!isLoaded) return;
    (async () => {
      try {
        const token = await getToken();
        const rows = await listProjects({ token });
        setProjects(rows);

        // Portfolio-wide "at risk" = sum of open critical (sev>=4) risks across
        // all projects. One query per project is fine at M2 scale; we'll batch
        // this into a dedicated endpoint when it starts to matter.
        if (rows.length > 0) {
          const counts = await Promise.all(
            rows.map(async (p) => {
              try {
                const risks = await listRisks(
                  p.id,
                  { severity_gte: 4, status: "open" },
                  { token }
                );
                return risks.length;
              } catch {
                return 0;
              }
            })
          );
          setAtRiskCount(counts.reduce((a, b) => a + b, 0));
        } else {
          setAtRiskCount(0);
        }
      } catch (err) {
        const msg =
          err instanceof ApiError
            ? `API ${err.status}: ${err.body ?? err.message}`
            : err instanceof Error
              ? err.message
              : "Failed to load dashboard";
        setError(msg);
        setProjects([]);
      }
    })();
  }, [getToken, isLoaded]);

  if (!isLoaded || projects === null) {
    return (
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-28 rounded-2xl" />
        ))}
      </div>
    );
  }

  const activeCount = projects.filter((p) => p.status === "active").length;
  const totalDocs = projects.reduce(
    (acc, p) => acc + (p.document_count ?? 0),
    0
  );
  const healths = projects
    .map((p) => p.health_score)
    .filter((h): h is number => typeof h === "number");
  const avgHealth =
    healths.length > 0
      ? Math.round(healths.reduce((a, b) => a + b, 0) / healths.length)
      : null;
  // Prefer the real critical-risk sum when it's landed; fall back to
  // health-score heuristic until the risks queries resolve.
  const atRisk =
    atRiskCount ??
    projects.filter(
      (p) => typeof p.health_score === "number" && p.health_score < 60
    ).length;

  return (
    <>
      {error ? (
        <div className="flex items-start gap-3 rounded-lg border border-destructive/40 bg-destructive/10 p-4 text-sm">
          <AlertTriangle className="mt-0.5 size-4 shrink-0 text-destructive" />
          <div className="flex-1">
            <p className="font-medium text-destructive">
              Could not reach the PMX API
            </p>
            <p className="text-muted-foreground">{error}</p>
          </div>
        </div>
      ) : null}

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatCard
          index={0}
          label="Active projects"
          value={activeCount.toString()}
          Icon={FolderKanban}
          hint={
            projects.length === 0
              ? "No projects yet"
              : `${projects.length} total`
          }
        />
        <StatCard
          index={1}
          label="At risk"
          value={atRisk.toString()}
          Icon={AlertCircle}
          hint={
            atRiskCount === null
              ? "Scanning projects…"
              : atRiskCount === 0
                ? "No critical open risks"
                : `${atRisk} critical open`
          }
        />
        <StatCard
          index={2}
          label="Total documents"
          value={totalDocs.toString()}
          Icon={FileText}
          hint={totalDocs === 0 ? "Upload to begin" : "across all projects"}
        />
        <StatCard
          index={3}
          label="Avg health"
          value={avgHealth?.toString() ?? "—"}
          Icon={Activity}
          hint={avgHealth === null ? "Score coming soon" : "portfolio-wide"}
        />
      </div>

      {projects.length === 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>Create your first project</CardTitle>
            <CardDescription>
              Projects are how PMX AI groups your documents, risks, and reports.
              Kick things off by adding one below.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button onClick={() => setDialogOpen(true)}>
              <Plus className="size-4" />
              New project
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          <div>
            <h2 className="font-display text-lg font-bold text-foreground">
              Recent projects
            </h2>
            <p className="text-sm text-muted-foreground">
              Newest first. Click one to open its risks, documents, and chat.
            </p>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            {projects.slice(0, 6).map((p, i) => (
              <ProjectCard key={p.id} project={p} index={i} />
            ))}
          </div>
        </div>
      )}

      <NewProjectDialog open={dialogOpen} onOpenChange={setDialogOpen} />
    </>
  );
}

type Band = {
  label: string;
  color: string;
};

function healthBand(score: number | null): Band {
  if (score === null) return { label: "No score", color: "#1B3E63" };
  if (score >= 75) return { label: "Healthy", color: "#35C97F" };
  if (score >= 50) return { label: "On watch", color: "#F2B233" };
  if (score >= 30) return { label: "At risk", color: "#F5893D" };
  return { label: "Critical", color: "#F65563" };
}

function formatSector(sector: Project["sector"]): string | null {
  if (!sector) return null;
  return sector.charAt(0).toUpperCase() + sector.slice(1);
}

const RING_RADIUS = 31;
const RING_CIRC = 2 * Math.PI * RING_RADIUS; // ≈ 194.8

function HealthRing({ score }: { score: number | null }) {
  const band = healthBand(score);
  const hasScore = typeof score === "number";
  const offset = hasScore ? RING_CIRC * (1 - (score as number) / 100) : RING_CIRC;

  return (
    <div className="relative size-[76px] shrink-0">
      <svg
        viewBox="0 0 76 76"
        className="size-[76px] -rotate-90"
        aria-hidden="true"
      >
        <circle
          cx="38"
          cy="38"
          r={RING_RADIUS}
          fill="none"
          stroke="#1B3E63"
          strokeWidth={7}
        />
        {hasScore ? (
          <circle
            cx="38"
            cy="38"
            r={RING_RADIUS}
            fill="none"
            stroke={band.color}
            strokeWidth={7}
            strokeLinecap="round"
            strokeDasharray={RING_CIRC}
            strokeDashoffset={offset}
          />
        ) : null}
      </svg>
      <div className="absolute inset-0 flex items-center justify-center">
        <span className="font-display text-[24px] font-bold tabular-nums text-foreground">
          {hasScore ? score : "—"}
        </span>
      </div>
    </div>
  );
}

function ProjectCard({ project, index }: { project: Project; index: number }) {
  const reduceMotion = useReducedMotion();
  const band = healthBand(project.health_score);
  const sector = formatSector(project.sector);
  const docCount = project.document_count ?? 0;

  // No per-project top-risk feed exists yet, so the footer surfaces the most
  // honest signal we do have: health-band status plus document coverage.
  const footerText =
    project.health_score === null
      ? "Awaiting first health score"
      : project.health_score < 50
        ? `Health below target${sector ? ` · ${sector}` : ""}`
        : docCount > 0
          ? `${docCount} document${docCount === 1 ? "" : "s"} tracked`
          : "No open risks";

  return (
    <motion.div
      initial={reduceMotion ? { opacity: 1, y: 0 } : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        duration: reduceMotion ? 0 : 0.28,
        delay: reduceMotion ? 0 : index * 0.05,
        ease: "easeOut",
      }}
    >
      <Link
        href={`/projects/${project.id}`}
        className="group block rounded-2xl border bg-card p-5 transition hover:-translate-y-0.5 hover:border-primary/60"
      >
        <div className="flex items-start gap-4">
          <HealthRing score={project.health_score} />
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span
                className="rounded-full px-2 py-0.5 text-[11px] font-bold"
                style={{
                  color: band.color,
                  backgroundColor: `${band.color}26`,
                }}
              >
                {band.label}
              </span>
              {sector ? (
                <span className="truncate text-xs text-muted-foreground">
                  {sector}
                </span>
              ) : null}
            </div>
            <p className="mt-2 truncate font-display font-bold text-foreground">
              {project.name}
            </p>
            <p className="truncate text-sm text-muted-foreground">
              {project.client ?? "—"}
            </p>
          </div>
        </div>

        <div className="mt-4 flex items-center gap-2 border-t pt-3">
          <span
            className="size-2 shrink-0 rounded-full"
            style={{ backgroundColor: band.color }}
          />
          <span className="text-[10px] font-bold uppercase tracking-wide text-muted-foreground">
            Top risk
          </span>
          <span className="truncate text-xs text-muted-foreground">
            {footerText}
          </span>
        </div>
      </Link>
    </motion.div>
  );
}

function StatCard({
  label,
  value,
  Icon,
  hint,
  index,
}: {
  label: string;
  value: string;
  Icon: React.ComponentType<{ className?: string }>;
  hint: string;
  index: number;
}) {
  const reduceMotion = useReducedMotion();
  return (
    <motion.div
      initial={reduceMotion ? { opacity: 1, y: 0 } : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        duration: reduceMotion ? 0 : 0.28,
        delay: reduceMotion ? 0 : index * 0.06,
        ease: "easeOut",
      }}
      className="rounded-2xl border bg-card p-5"
    >
      <div className="flex items-start justify-between">
        <span className="text-sm text-muted-foreground">{label}</span>
        <span className="flex size-8 items-center justify-center rounded-lg bg-accent">
          <Icon className="size-4 text-muted-foreground" />
        </span>
      </div>
      <p className="mt-3 font-display text-3xl font-bold tabular-nums text-foreground">
        {value}
      </p>
      <p className="mt-1 text-xs text-muted-foreground">{hint}</p>
    </motion.div>
  );
}
