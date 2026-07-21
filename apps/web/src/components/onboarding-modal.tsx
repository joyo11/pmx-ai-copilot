"use client";

import * as React from "react";
import { ChevronsRight, Upload } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";

const STORAGE_KEY = "pmx_onboarded";

const STEPS = [
  {
    title: "Connect your project documents",
    body: "Drop in schedules, cost reports, RFIs, and meeting minutes — Primavera P6, MS Project, Excel, PDF, and DOCX. PMX AI reads them the way an experienced PM would.",
  },
  {
    title: "AI scores health & flags risk",
    body: "PMX AI computes a live health score and ranks the risks — budget overruns, schedule slips, overdue RFIs — each quantified in dollars and days.",
  },
  {
    title: "Ask anything, cited",
    body: "Ask in plain English. Every answer is grounded in your documents and cites the exact source page, so you can trust it and verify it.",
  },
] as const;

export function OnboardingModal() {
  const [open, setOpen] = React.useState(false);
  const [step, setStep] = React.useState(0);

  React.useEffect(() => {
    try {
      if (localStorage.getItem(STORAGE_KEY) !== "1") {
        setOpen(true);
      }
    } catch {
      // localStorage unavailable (SSR / privacy mode) — stay closed
    }
  }, []);

  const finish = React.useCallback(() => {
    try {
      localStorage.setItem(STORAGE_KEY, "1");
    } catch {
      // ignore write failures
    }
    setOpen(false);
  }, []);

  const isLast = step === STEPS.length - 1;

  function handleNext() {
    if (isLast) {
      finish();
    } else {
      setStep((s) => s + 1);
    }
  }

  function handleOpenChange(next: boolean) {
    // Closing via overlay / X / Esc counts as dismissing onboarding.
    if (!next) finish();
    else setOpen(next);
  }

  const current = STEPS[step];

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent
        showCloseButton={false}
        className="overflow-hidden p-0 sm:max-w-md"
      >
        {/* Header band */}
        <div
          className="relative flex h-32 items-center justify-center"
          style={{
            background: "linear-gradient(140deg, #0B4E9E, #1E7FE0)",
          }}
        >
          <ChevronsRight
            className="pointer-events-none absolute right-4 top-4 size-16 text-white/10"
            aria-hidden
          />
          <ChevronsRight
            className="pointer-events-none absolute left-4 bottom-4 size-10 text-white/10"
            aria-hidden
          />
          <div className="flex size-16 items-center justify-center rounded-2xl bg-white/15 backdrop-blur-sm">
            <Upload className="size-8 text-white" aria-hidden />
          </div>
        </div>

        {/* Body */}
        <div className="flex flex-col gap-4 px-6 pb-6 pt-5">
          {/* Progress segments */}
          <div className="flex items-center gap-1.5" aria-hidden>
            {STEPS.map((_, i) => (
              <span
                key={i}
                className={cn(
                  "h-1.5 flex-1 rounded-full transition-colors",
                  i <= step ? "bg-primary" : "bg-secondary"
                )}
              />
            ))}
          </div>

          <p className="text-xs font-bold text-primary">
            Step {step + 1} of {STEPS.length}
          </p>

          <div className="flex flex-col gap-2">
            <DialogTitle className="font-display text-xl font-bold text-foreground">
              {current.title}
            </DialogTitle>
            <DialogDescription className="text-sm leading-relaxed text-muted-foreground">
              {current.body}
            </DialogDescription>
          </div>

          {/* Footer */}
          <div className="mt-2 flex items-center justify-between">
            <Button
              variant="ghost"
              size="sm"
              onClick={finish}
              className="text-muted-foreground"
            >
              Skip
            </Button>
            <Button size="sm" onClick={handleNext}>
              {isLast ? "Get started" : "Next"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
