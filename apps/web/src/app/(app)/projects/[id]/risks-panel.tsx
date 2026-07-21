"use client";

import * as React from "react";
import { useAuth } from "@clerk/nextjs";
import { toast } from "sonner";
import {
  AlertTriangle,
  ChevronRight,
  FileText,
  RefreshCw,
  Sparkles,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { cn } from "@/lib/utils";
import {
  CitationChip,
  citationKey,
} from "@/components/citation-chip";
import {
  ApiError,
  getRisk,
  listRisks,
  scanProjectRisks,
  updateRiskStatus,
  type ListRisksFilters,
  type RiskCategory,
  type RiskDetail,
  type RiskStatus,
  type RiskSummary,
} from "@/lib/api";

const CATEGORIES: { key: RiskCategory | "all"; label: string }[] = [
  { key: "all", label: "All" },
  { key: "schedule", label: "Schedule" },
  { key: "budget", label: "Budget" },
  { key: "operational", label: "Operational" },
  { key: "communication", label: "Communication" },
  { key: "compliance", label: "Compliance" },
];

const SEVERITY_STYLES: Record<
  number,
  { border: string; label: string; text: string }
> = {
  1: {
    border: "border-l-emerald-500",
    label: "Sev 1",
    text: "text-emerald-600 dark:text-emerald-400",
  },
  2: {
    border: "border-l-yellow-500",
    label: "Sev 2",
    text: "text-yellow-600 dark:text-yellow-400",
  },
  3: {
    border: "border-l-orange-500",
    label: "Sev 3",
    text: "text-orange-600 dark:text-orange-400",
  },
  4: {
    border: "border-l-red-500",
    label: "Sev 4",
    text: "text-red-600 dark:text-red-400",
  },
  5: {
    border: "border-l-red-800",
    label: "Sev 5",
    text: "text-red-700 dark:text-red-500",
  },
};

/** Handoff risk palette (severity → hex). 5 folds into critical red. */
const SEVERITY_HEX: Record<number, string> = {
  1: "#35C97F",
  2: "#F2B233",
  3: "#F5893D",
  4: "#F65563",
  5: "#F65563",
};

function sevHex(severity: number): string {
  return SEVERITY_HEX[severity] ?? "#F5893D";
}

/**
 * A concise exposure string for the right-most column. Prefer a dollar/impact
 * figure lifted from the title or business_impact; fall back to a truncated
 * business_impact, then to the severity label.
 */
function exposureLabel(r: RiskSummary): string {
  const hay = `${r.title} ${r.business_impact ?? ""}`;
  const money = hay.match(
    /\$\s?\d[\d,]*(?:\.\d+)?\s?(?:[KkMmBb]\b|million|billion|thousand)?/
  );
  if (money) return money[0].replace(/\s+/g, " ").trim();
  const impact = r.business_impact?.trim();
  if (impact) return impact.length > 16 ? `${impact.slice(0, 15).trimEnd()}…` : impact;
  return `Sev ${r.severity}`;
}

function statusVariant(
  status: RiskStatus
): "default" | "secondary" | "outline" | "destructive" {
  switch (status) {
    case "open":
      return "destructive";
    case "acknowledged":
      return "default";
    case "mitigated":
      return "secondary";
    case "resolved":
      return "outline";
  }
}

export function RisksPanel({
  projectId,
  onCountsChange,
}: {
  projectId: string;
  /** Called whenever the visible risk list refreshes, with critical (>=4) open count. */
  onCountsChange?: (criticalOpen: number) => void;
}) {
  const { getToken } = useAuth();

  const [risks, setRisks] = React.useState<RiskSummary[] | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const [category, setCategory] = React.useState<RiskCategory | "all">("all");
  const [severityGte, setSeverityGte] = React.useState<number>(1);

  const [scanning, setScanning] = React.useState(false);
  const [selectedId, setSelectedId] = React.useState<string | null>(null);
  const [detail, setDetail] = React.useState<RiskDetail | null>(null);
  const [detailLoading, setDetailLoading] = React.useState(false);
  const [detailError, setDetailError] = React.useState<string | null>(null);

  const refresh = React.useCallback(async () => {
    setError(null);
    try {
      const token = await getToken();
      const filters: ListRisksFilters | undefined =
        category === "all" && severityGte <= 1
          ? undefined
          : {
              category: category === "all" ? undefined : category,
              severity_gte: severityGte > 1 ? severityGte : undefined,
            };
      const rows = await listRisks(projectId, filters, { token });
      setRisks(rows);
      // Only propagate a count when we're viewing the unfiltered set —
      // otherwise a category filter would falsely lower the tab badge.
      if (category === "all" && severityGte <= 1) {
        const critical = rows.filter(
          (r) => r.severity >= 4 && r.status === "open"
        ).length;
        onCountsChange?.(critical);
      }
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? `API ${err.status}: ${err.body ?? err.message}`
          : err instanceof Error
            ? err.message
            : "Failed to load risks";
      setError(msg);
      setRisks([]);
    }
  }, [category, getToken, onCountsChange, projectId, severityGte]);

  React.useEffect(() => {
    void refresh();
  }, [refresh]);

  async function onScan() {
    if (scanning) return;
    setScanning(true);
    try {
      const token = await getToken();
      await scanProjectRisks(projectId, { token });
      toast.success("Risk scan started");
      await refresh();
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? `API ${err.status}: ${err.body ?? err.message}`
          : err instanceof Error
            ? err.message
            : "Scan failed";
      toast.error(msg);
    } finally {
      setScanning(false);
    }
  }

  async function onStatusChange(
    id: string,
    status: Exclude<RiskStatus, "open">
  ) {
    try {
      const token = await getToken();
      const updated = await updateRiskStatus(id, status, { token });
      setRisks((prev) =>
        prev
          ? prev.map((r) => (r.id === id ? { ...r, ...updated } : r))
          : prev
      );
      toast.success(`Marked ${status}`);
      // Detail sheet mirrors the change if open.
      setDetail((prev) => (prev && prev.id === id ? { ...prev, ...updated } : prev));
      // Refresh the critical-open count for the tab badge.
      try {
        const rows = await listRisks(
          projectId,
          { severity_gte: 4, status: "open" },
          { token }
        );
        onCountsChange?.(rows.length);
      } catch {
        // non-fatal
      }
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? `API ${err.status}: ${err.body ?? err.message}`
          : err instanceof Error
            ? err.message
            : "Update failed";
      toast.error(msg);
    }
  }

  const openDetail = React.useCallback(
    async (id: string) => {
      setSelectedId(id);
      setDetail(null);
      setDetailError(null);
      setDetailLoading(true);
      try {
        const token = await getToken();
        const d = await getRisk(id, { token });
        setDetail(d);
      } catch (err) {
        const msg =
          err instanceof ApiError
            ? `API ${err.status}: ${err.body ?? err.message}`
            : err instanceof Error
              ? err.message
              : "Failed to load risk";
        setDetailError(msg);
      } finally {
        setDetailLoading(false);
      }
    },
    [getToken]
  );

  return (
    <div className="space-y-4">
      {/* Filter row */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex flex-wrap gap-1.5">
          {CATEGORIES.map((c) => (
            <button
              key={c.key}
              type="button"
              onClick={() => setCategory(c.key)}
              className={cn(
                "inline-flex min-h-8 items-center rounded-full border px-3.5 text-xs font-medium transition-colors",
                category === c.key
                  ? "border-primary bg-primary text-primary-foreground"
                  : "border bg-card text-muted-foreground hover:text-foreground"
              )}
            >
              {c.label}
            </button>
          ))}
        </div>

        <div className="ml-auto flex flex-wrap items-center gap-3">
          {risks ? (
            <span className="text-xs tabular-nums text-muted-foreground">
              {risks.length} {risks.length === 1 ? "risk" : "risks"}
            </span>
          ) : null}
          <div className="flex items-center gap-2 rounded-full border bg-card px-3 py-1.5">
            <span className="text-xs text-muted-foreground">Severity ≥</span>
            <input
              type="range"
              min={1}
              max={5}
              step={1}
              value={severityGte}
              onChange={(e) => setSeverityGte(Number(e.target.value))}
              className="w-20 accent-primary"
              aria-label="Minimum severity"
            />
            <span className="w-4 text-center text-xs font-semibold tabular-nums">
              {severityGte}
            </span>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => void onScan()}
            disabled={scanning}
          >
            <RefreshCw className={cn("size-4", scanning && "animate-spin")} />
            {scanning ? "Scanning…" : "Refresh scan"}
          </Button>
        </div>
      </div>

      {error ? (
        <div className="flex items-start gap-3 rounded-2xl border border-destructive/40 bg-destructive/10 p-4 text-sm">
          <AlertTriangle className="mt-0.5 size-4 shrink-0 text-destructive" />
          <div className="flex-1">
            <p className="font-medium text-destructive">Could not load risks</p>
            <p className="text-muted-foreground">{error}</p>
          </div>
          <Button size="sm" variant="outline" onClick={() => void refresh()}>
            Retry
          </Button>
        </div>
      ) : null}

      {risks === null ? (
        <div className="space-y-2">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-16 rounded-2xl" />
          ))}
        </div>
      ) : risks.length === 0 ? (
        <EmptyState onScan={onScan} scanning={scanning} />
      ) : (
        <div className="overflow-hidden rounded-2xl border bg-card">
          <div className="overflow-x-auto">
            <div className="min-w-[720px]">
              {/* Header */}
              <div className="grid grid-cols-[44px_1fr_130px_110px_120px_40px] items-center gap-3 bg-secondary px-5 py-[13px] text-[11px] font-bold uppercase tracking-wide text-muted-foreground">
                <div>Sev</div>
                <div>Risk</div>
                <div>Category</div>
                <div>Likelihood</div>
                <div className="text-right">Exposure</div>
                <div />
              </div>

              {/* Rows */}
              {risks.map((r) => {
                const hex = sevHex(r.severity);
                return (
                  <div
                    key={r.id}
                    role="button"
                    tabIndex={0}
                    onClick={() => void openDetail(r.id)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        void openDetail(r.id);
                      }
                    }}
                    className="grid cursor-pointer grid-cols-[44px_1fr_130px_110px_120px_40px] items-center gap-3 border-b px-5 py-3 outline-none transition-colors last:border-b-0 hover:bg-secondary focus-visible:bg-secondary"
                  >
                    {/* Sev */}
                    <div
                      className="flex size-[30px] items-center justify-center rounded-lg"
                      style={{ backgroundColor: `${hex}26` }}
                    >
                      <AlertTriangle className="size-4" style={{ color: hex }} />
                    </div>

                    {/* Risk */}
                    <div className="min-w-0">
                      <p className="truncate font-medium text-foreground">
                        {r.title}
                      </p>
                      <div className="mt-0.5 flex items-center gap-1 text-[12px] text-muted-foreground">
                        <FileText className="size-3 shrink-0" />
                        <span className="truncate capitalize">
                          {r.category}
                        </span>
                      </div>
                    </div>

                    {/* Category */}
                    <div>
                      <span className="inline-flex items-center rounded-full border bg-secondary px-2 py-0.5 text-[11px] capitalize text-muted-foreground">
                        {r.category}
                      </span>
                    </div>

                    {/* Likelihood */}
                    <div className="text-[13px] tabular-nums text-muted-foreground">
                      {Math.round((r.likelihood ?? 0) * 100)}%
                    </div>

                    {/* Exposure */}
                    <div
                      className="truncate text-right font-display font-bold tabular-nums"
                      style={{ color: hex }}
                    >
                      {exposureLabel(r)}
                    </div>

                    {/* Chevron */}
                    <div className="flex justify-end">
                      <ChevronRight className="size-4 text-muted-foreground" />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      <RiskDetailSheet
        open={selectedId !== null}
        loading={detailLoading}
        error={detailError}
        risk={detail}
        onClose={() => {
          setSelectedId(null);
          setDetail(null);
          setDetailError(null);
        }}
        onStatusChange={onStatusChange}
      />
    </div>
  );
}

function EmptyState({
  onScan,
  scanning,
}: {
  onScan: () => void | Promise<void>;
  scanning: boolean;
}) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-2xl border border-dashed bg-card p-10 text-center">
      <div className="flex size-12 items-center justify-center rounded-full bg-muted">
        <Sparkles className="size-5 text-muted-foreground" />
      </div>
      <div className="space-y-1">
        <p className="text-sm font-medium">No risks yet</p>
        <p className="max-w-sm text-xs text-muted-foreground">
          Run a scan to have the AI review your uploaded documents and surface
          risks by category and severity.
        </p>
      </div>
      <Button
        size="sm"
        onClick={() => void onScan()}
        disabled={scanning}
      >
        <RefreshCw className={cn("size-4", scanning && "animate-spin")} />
        {scanning ? "Scanning…" : "Run risk scan"}
      </Button>
    </div>
  );
}

function RiskDetailSheet({
  open,
  onClose,
  risk,
  loading,
  error,
  onStatusChange,
}: {
  open: boolean;
  onClose: () => void;
  risk: RiskDetail | null;
  loading: boolean;
  error: string | null;
  onStatusChange: (
    id: string,
    status: Exclude<RiskStatus, "open">
  ) => void | Promise<void>;
}) {
  return (
    <Sheet open={open} onOpenChange={(v) => (v ? undefined : onClose())}>
      <SheetContent className="flex w-full flex-col gap-0 overflow-y-auto sm:max-w-lg">
        {loading ? (
          <div className="space-y-3 p-6">
            <Skeleton className="h-6 w-3/4" />
            <Skeleton className="h-4 w-1/2" />
            <Skeleton className="h-24 w-full" />
          </div>
        ) : error ? (
          <div className="flex items-start gap-3 p-6 text-sm">
            <AlertTriangle className="mt-0.5 size-4 shrink-0 text-destructive" />
            <div>
              <p className="font-medium text-destructive">
                Could not load risk
              </p>
              <p className="text-muted-foreground">{error}</p>
            </div>
          </div>
        ) : risk ? (
          <>
            <SheetHeader className="border-b p-6">
              <div className="flex flex-wrap items-center gap-2">
                <Badge
                  variant="outline"
                  className={cn(
                    "capitalize",
                    SEVERITY_STYLES[risk.severity]?.text
                  )}
                >
                  {SEVERITY_STYLES[risk.severity]?.label ??
                    `Sev ${risk.severity}`}
                </Badge>
                <Badge variant="secondary" className="capitalize">
                  {risk.category}
                </Badge>
                <Badge
                  variant={statusVariant(risk.status)}
                  className="capitalize"
                >
                  {risk.status}
                </Badge>
              </div>
              <SheetTitle className="pr-8 text-lg leading-tight">
                {risk.title}
              </SheetTitle>
              <SheetDescription className="flex flex-wrap gap-4 text-xs">
                <span>
                  Likelihood {Math.round((risk.likelihood ?? 0) * 100)}%
                </span>
                {typeof risk.confidence === "number" ? (
                  <span>
                    Confidence {Math.round(risk.confidence * 100)}%
                  </span>
                ) : null}
              </SheetDescription>
            </SheetHeader>

            <div className="flex-1 space-y-6 p-6">
              <Section title="Description">
                <p className="whitespace-pre-wrap text-sm leading-relaxed text-muted-foreground">
                  {risk.description}
                </p>
              </Section>
              {risk.business_impact ? (
                <Section title="Business impact">
                  <p className="whitespace-pre-wrap text-sm leading-relaxed text-muted-foreground">
                    {risk.business_impact}
                  </p>
                </Section>
              ) : null}
              {risk.recommended_action ? (
                <Section title="Recommended action">
                  <p className="whitespace-pre-wrap text-sm leading-relaxed text-muted-foreground">
                    {risk.recommended_action}
                  </p>
                </Section>
              ) : null}
              {(risk.citations ?? []).length > 0 ? (
                <Section title="Citations">
                  <div className="flex flex-wrap gap-1.5">
                    {(risk.citations ?? []).map((c, i) => (
                      <CitationChip
                        key={citationKey(c) + i}
                        citation={c}
                      />
                    ))}
                  </div>
                </Section>
              ) : null}
            </div>

            <div
              className="flex flex-wrap gap-2 border-t bg-background p-4"
              style={{
                paddingBottom: "max(1rem, env(safe-area-inset-bottom))",
              }}
            >
              <Button
                size="sm"
                variant="outline"
                disabled={risk.status === "acknowledged"}
                onClick={() => void onStatusChange(risk.id, "acknowledged")}
              >
                Acknowledge
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={risk.status === "mitigated"}
                onClick={() => void onStatusChange(risk.id, "mitigated")}
              >
                Mark mitigated
              </Button>
              <Button
                size="sm"
                disabled={risk.status === "resolved"}
                onClick={() => void onStatusChange(risk.id, "resolved")}
              >
                Resolve
              </Button>
            </div>
          </>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-2">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {title}
      </h3>
      {children}
    </div>
  );
}
