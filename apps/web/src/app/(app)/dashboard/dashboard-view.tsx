"use client";

import * as React from "react";
import Link from "next/link";
import { useAuth } from "@clerk/nextjs";
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
          <Skeleton key={i} className="h-28 rounded-xl" />
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
          label="Total documents"
          value={totalDocs.toString()}
          Icon={FileText}
          hint={totalDocs === 0 ? "Upload to begin" : "across all projects"}
        />
        <StatCard
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
        <Card>
          <CardHeader>
            <CardTitle>Recent projects</CardTitle>
            <CardDescription>
              Newest first. Click one to open its risks, documents, and chat.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {projects.slice(0, 5).map((p) => (
              <Link
                key={p.id}
                href={`/projects/${p.id}`}
                className="flex items-center justify-between rounded-md border p-3 text-sm transition-colors hover:bg-accent/40"
              >
                <div className="min-w-0">
                  <p className="truncate font-medium">{p.name}</p>
                  <p className="truncate text-xs text-muted-foreground">
                    {p.client ?? "—"}
                    {p.sector ? ` · ${p.sector}` : ""}
                  </p>
                </div>
                <span className="tabular-nums text-xs text-muted-foreground">
                  Health {p.health_score ?? "—"}
                </span>
              </Link>
            ))}
          </CardContent>
        </Card>
      )}

      <NewProjectDialog open={dialogOpen} onOpenChange={setDialogOpen} />
    </>
  );
}

function StatCard({
  label,
  value,
  Icon,
  hint,
}: {
  label: string;
  value: string;
  Icon: React.ComponentType<{ className?: string }>;
  hint: string;
}) {
  return (
    <Card>
      <CardHeader>
        <CardDescription className="flex items-center justify-between">
          <span>{label}</span>
          <Icon className="size-4 text-muted-foreground" />
        </CardDescription>
        <CardTitle className="text-3xl font-semibold tabular-nums">
          {value}
        </CardTitle>
      </CardHeader>
      <CardContent className="text-xs text-muted-foreground">{hint}</CardContent>
    </Card>
  );
}
