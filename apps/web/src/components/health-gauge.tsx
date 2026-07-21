"use client";

import * as React from "react";
import {
  animate,
  motion,
  useMotionValue,
  useReducedMotion,
  useTransform,
} from "motion/react";
import { ChevronDown, RefreshCw, AlertTriangle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { HealthSnapshot, HealthFactor } from "@/lib/api";

interface HealthGaugeProps {
  snapshot: HealthSnapshot | null;
  loading?: boolean;
  error?: string | null;
  onRecompute?: () => void | Promise<void>;
  recomputing?: boolean;
  /** When true, the "Compute health" button is disabled with an upload hint. */
  hasDocuments?: boolean;
}

/** Bucket color used by the ring, number, and the "why?" pill. */
function colorFor(score: number): {
  ring: string;
  text: string;
  bg: string;
  label: string;
} {
  if (score >= 80)
    return {
      ring: "stroke-emerald-500",
      text: "text-emerald-600 dark:text-emerald-400",
      bg: "bg-emerald-500",
      label: "Healthy",
    };
  if (score >= 60)
    return {
      ring: "stroke-yellow-500",
      text: "text-yellow-600 dark:text-yellow-400",
      bg: "bg-yellow-500",
      label: "Watch",
    };
  if (score >= 40)
    return {
      ring: "stroke-orange-500",
      text: "text-orange-600 dark:text-orange-400",
      bg: "bg-orange-500",
      label: "At risk",
    };
  return {
    ring: "stroke-red-500",
    text: "text-red-600 dark:text-red-400",
    bg: "bg-red-500",
    label: "Critical",
  };
}

const RADIUS = 56;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

export function HealthGauge({
  snapshot,
  loading,
  error,
  onRecompute,
  recomputing,
  hasDocuments = true,
}: HealthGaugeProps) {
  const [showReasoning, setShowReasoning] = React.useState(false);

  if (loading && !snapshot) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center gap-4 py-8">
          <Skeleton className="size-36 rounded-full" />
          <Skeleton className="h-4 w-40" />
          <Skeleton className="h-3 w-full max-w-sm" />
        </CardContent>
      </Card>
    );
  }

  if (error && !snapshot) {
    return (
      <Card>
        <CardContent className="flex items-start gap-3 py-6 text-sm">
          <AlertTriangle className="mt-0.5 size-4 shrink-0 text-destructive" />
          <div className="flex-1">
            <p className="font-medium text-destructive">
              Could not load health score
            </p>
            <p className="text-muted-foreground">{error}</p>
          </div>
          {onRecompute ? (
            <Button
              size="sm"
              variant="outline"
              onClick={() => void onRecompute()}
              disabled={recomputing}
            >
              Retry
            </Button>
          ) : null}
        </CardContent>
      </Card>
    );
  }

  if (!snapshot) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center gap-3 py-8 text-center">
          <p className="text-sm font-medium">No health score yet</p>
          <p className="max-w-sm text-xs text-muted-foreground">
            {hasDocuments
              ? "Run a risk scan or compute the score to see how this project is doing."
              : "Upload at least one document first, then compute a health score."}
          </p>
          {onRecompute ? (
            <Button
              size="sm"
              onClick={() => void onRecompute()}
              disabled={recomputing || !hasDocuments}
              title={!hasDocuments ? "Upload a document first" : undefined}
            >
              <RefreshCw
                className={cn("size-4", recomputing && "animate-spin")}
              />
              Compute health
            </Button>
          ) : null}
        </CardContent>
      </Card>
    );
  }

  const score = Math.max(0, Math.min(100, Math.round(snapshot.score)));
  const color = colorFor(score);
  const factors = snapshot.factors ?? [];
  // Weight-normalized fill so a low-weight factor doesn't dominate visually.
  const totalWeight =
    factors.reduce((acc, f) => acc + (f.weight ?? 0), 0) || 1;

  return (
    <Card>
      <CardContent className="grid gap-6 py-6 md:grid-cols-[auto_1fr] md:items-start">
        <div className="flex flex-col items-center gap-3 md:items-start">
          <div className="relative size-56">
            <AnimatedRing score={score} ringClass={color.ring} />
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <AnimatedScore
                score={score}
                className={cn(
                  "font-display text-6xl font-bold tabular-nums leading-none",
                  color.text
                )}
              />
              <span className="mt-1 text-xs text-muted-foreground">
                / 100
              </span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium text-white",
                color.bg
              )}
            >
              {color.label}
            </span>
            {onRecompute ? (
              <Button
                size="sm"
                variant="ghost"
                onClick={() => void onRecompute()}
                disabled={recomputing}
                className="h-8 gap-1.5"
              >
                <RefreshCw
                  className={cn("size-3.5", recomputing && "animate-spin")}
                />
                Recompute
              </Button>
            ) : null}
          </div>
          <p className="text-[10px] uppercase tracking-wide text-muted-foreground">
            Updated {new Date(snapshot.computed_at).toLocaleString()}
          </p>
        </div>

        <div className="space-y-4">
          <div>
            <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Contributing factors
            </p>
            {factors.length === 0 ? (
              <p className="text-xs text-muted-foreground">
                No factor breakdown available.
              </p>
            ) : (
              <ul className="space-y-2">
                {factors.slice(0, 4).map((f, i) => (
                  <FactorBar
                    key={f.key}
                    factor={f}
                    weightShare={(f.weight ?? 0) / totalWeight}
                    index={i}
                  />
                ))}
              </ul>
            )}
          </div>

          {snapshot.reasoning ? (
            <div>
              <button
                type="button"
                onClick={() => setShowReasoning((v) => !v)}
                className="inline-flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground"
                aria-expanded={showReasoning}
              >
                <ChevronDown
                  className={cn(
                    "size-3.5 transition-transform",
                    showReasoning && "rotate-180"
                  )}
                />
                Why this score?
              </button>
              {showReasoning ? (
                <p className="mt-2 whitespace-pre-wrap rounded-md border bg-muted/40 p-3 text-xs leading-relaxed text-muted-foreground">
                  {snapshot.reasoning}
                </p>
              ) : null}
            </div>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}

function FactorBar({
  factor,
  weightShare,
  index,
}: {
  factor: HealthFactor;
  weightShare: number;
  index: number;
}) {
  const reduceMotion = useReducedMotion();
  const score = Math.max(0, Math.min(100, Math.round(factor.score ?? 0)));
  const color = colorFor(score);
  const label =
    factor.label ??
    factor.key
      .replace(/[_-]+/g, " ")
      .replace(/\b\w/g, (c) => c.toUpperCase());
  return (
    <li className="space-y-1">
      <div className="flex items-center justify-between gap-3 text-xs">
        <span className="truncate font-medium">{label}</span>
        <span className="tabular-nums text-muted-foreground">
          {score}
          <span className="ml-1 text-[10px]">
            · w{Math.round(weightShare * 100)}%
          </span>
        </span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-muted">
        <motion.div
          key={`${factor.key}-${score}`}
          className={cn("h-full rounded-full", color.bg)}
          initial={reduceMotion ? { width: `${score}%` } : { width: 0 }}
          animate={{ width: `${score}%` }}
          transition={
            reduceMotion
              ? { duration: 0 }
              : {
                  duration: 0.8,
                  delay: 0.1 + index * 0.08,
                  ease: [0.16, 1, 0.3, 1],
                }
          }
        />
      </div>
    </li>
  );
}

function AnimatedScore({
  score,
  className,
}: {
  score: number;
  className?: string;
}) {
  const reduceMotion = useReducedMotion();
  const mv = useMotionValue(reduceMotion ? score : 0);
  const rounded = useTransform(mv, (v) => Math.round(v));
  const [display, setDisplay] = React.useState(reduceMotion ? score : 0);

  // Subscribe to motion-value changes and mirror them into React state.
  // `rounded.on("change")` fires from motion's animation frame — not a
  // synchronous setState in the effect body.
  React.useEffect(() => {
    return rounded.on("change", (v) => setDisplay(v));
  }, [rounded]);

  React.useEffect(() => {
    if (reduceMotion) {
      // Snap the motion value; the subscription above updates `display`.
      mv.set(score);
      return;
    }
    const controls = animate(mv, score, {
      duration: 0.8,
      ease: [0.16, 1, 0.3, 1],
    });
    return () => controls.stop();
  }, [mv, score, reduceMotion]);

  return <span className={className}>{display}</span>;
}

function AnimatedRing({
  score,
  ringClass,
}: {
  score: number;
  ringClass: string;
}) {
  const reduceMotion = useReducedMotion();
  const target = CIRCUMFERENCE * (1 - score / 100);
  return (
    <svg viewBox="0 0 128 128" className="size-full -rotate-90" aria-hidden>
      <circle
        cx="64"
        cy="64"
        r={RADIUS}
        strokeWidth="10"
        className="fill-none stroke-muted"
      />
      <motion.circle
        cx="64"
        cy="64"
        r={RADIUS}
        strokeWidth="10"
        strokeLinecap="round"
        className={cn("fill-none", ringClass)}
        strokeDasharray={CIRCUMFERENCE}
        initial={
          reduceMotion
            ? { strokeDashoffset: target }
            : { strokeDashoffset: CIRCUMFERENCE }
        }
        animate={{ strokeDashoffset: target }}
        transition={
          reduceMotion
            ? { duration: 0 }
            : { duration: 0.8, ease: [0.16, 1, 0.3, 1] }
        }
      />
    </svg>
  );
}
