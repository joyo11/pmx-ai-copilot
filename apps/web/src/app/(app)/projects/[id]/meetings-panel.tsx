"use client";

import * as React from "react";
import { useAuth } from "@clerk/nextjs";
import { toast } from "sonner";
import {
  CalendarDays,
  CheckCircle2,
  FileText,
  Loader2,
  Plus,
  Sparkles,
  Upload,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import {
  analyzeMeeting,
  ApiError,
  getMeeting,
  listMeetings,
  type MeetingActionItem,
  type MeetingDetail,
  type MeetingSummary,
} from "@/lib/api";

const ACCEPT = ".txt,.docx,.pdf,text/plain,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document";

export function MeetingsPanel({
  projectId,
  onSwitchToRisks,
}: {
  projectId: string;
  onSwitchToRisks?: () => void;
}) {
  const { getToken } = useAuth();
  const [meetings, setMeetings] = React.useState<MeetingSummary[] | null>(null);
  const [loadError, setLoadError] = React.useState<string | null>(null);
  const [dialogOpen, setDialogOpen] = React.useState(false);
  const [analyzing, setAnalyzing] = React.useState(false);
  const [openMeetingId, setOpenMeetingId] = React.useState<string | null>(null);
  const [openMeeting, setOpenMeeting] = React.useState<MeetingDetail | null>(
    null
  );
  const [detailLoading, setDetailLoading] = React.useState(false);

  const refresh = React.useCallback(async () => {
    setLoadError(null);
    try {
      const token = await getToken();
      const rows = await listMeetings(projectId, { token });
      setMeetings(rows);
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? `API ${err.status}: ${err.body ?? err.message}`
          : err instanceof Error
            ? err.message
            : "Failed to load meetings";
      setLoadError(msg);
    }
  }, [getToken, projectId]);

  React.useEffect(() => {
    void refresh();
  }, [refresh]);

  const openDetail = React.useCallback(
    async (meetingId: string) => {
      setOpenMeetingId(meetingId);
      setDetailLoading(true);
      setOpenMeeting(null);
      try {
        const token = await getToken();
        const detail = await getMeeting(meetingId, { token });
        setOpenMeeting(detail);
      } catch (err) {
        toast.error(
          err instanceof Error ? err.message : "Failed to load meeting"
        );
        setOpenMeetingId(null);
      } finally {
        setDetailLoading(false);
      }
    },
    [getToken]
  );

  const handleAnalyze = React.useCallback(
    async (opts: {
      transcriptText?: string;
      file?: File;
      meetingDate?: string;
    }) => {
      if (analyzing) return;
      setAnalyzing(true);
      try {
        const token = await getToken();
        const result = await analyzeMeeting(
          {
            projectId,
            transcriptText: opts.transcriptText,
            file: opts.file,
            meetingDate: opts.meetingDate,
          },
          { token }
        );
        toast.success(
          result.risks_created > 0
            ? `Meeting analyzed: ${result.risks_created} risk(s) surfaced`
            : "Meeting analyzed"
        );
        setDialogOpen(false);
        await refresh();
        await openDetail(result.meeting_id);
      } catch (err) {
        const msg =
          err instanceof ApiError
            ? err.status === 503
              ? "Meeting Intelligence needs ANTHROPIC_API_KEY on the API. Ask your admin."
              : `API ${err.status}: ${err.body ?? err.message}`
            : err instanceof Error
              ? err.message
              : "Analyze failed";
        toast.error(msg);
      } finally {
        setAnalyzing(false);
      }
    },
    [analyzing, getToken, openDetail, projectId, refresh]
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold">Meetings</h3>
          <p className="text-sm text-muted-foreground">
            Drop a transcript, get an executive summary, action items, and
            surfaced risks.
          </p>
        </div>
        <Button onClick={() => setDialogOpen(true)} className="gap-1.5">
          <Plus className="size-4" /> New meeting
        </Button>
      </div>

      {loadError ? (
        <div className="rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
          {loadError}
        </div>
      ) : null}

      {meetings === null ? (
        <div className="space-y-2">
          <Skeleton className="h-20 rounded-lg" />
          <Skeleton className="h-20 rounded-lg" />
        </div>
      ) : meetings.length === 0 ? (
        <EmptyState onNew={() => setDialogOpen(true)} />
      ) : (
        <div className="space-y-2">
          {meetings.map((m) => (
            <MeetingRow key={m.id} meeting={m} onOpen={() => openDetail(m.id)} />
          ))}
        </div>
      )}

      <NewMeetingDialog
        open={dialogOpen}
        onOpenChange={(v) => (!analyzing ? setDialogOpen(v) : null)}
        onSubmit={handleAnalyze}
        analyzing={analyzing}
      />

      <Sheet
        open={openMeetingId !== null}
        onOpenChange={(v) => {
          if (!v) {
            setOpenMeetingId(null);
            setOpenMeeting(null);
          }
        }}
      >
        <SheetContent side="right" className="w-full sm:max-w-xl">
          <SheetHeader>
            <SheetTitle>Meeting detail</SheetTitle>
            <SheetDescription>
              Summary, action items, decisions, and any risks that came up.
            </SheetDescription>
          </SheetHeader>
          <div className="mt-4 space-y-6 px-4 pb-6">
            {detailLoading ? (
              <div className="space-y-2">
                <Skeleton className="h-4 rounded" />
                <Skeleton className="h-4 rounded w-3/4" />
                <Skeleton className="h-32 rounded" />
              </div>
            ) : openMeeting ? (
              <MeetingDetailView
                detail={openMeeting}
                onGoToRisks={onSwitchToRisks}
              />
            ) : null}
          </div>
        </SheetContent>
      </Sheet>
    </div>
  );
}

function EmptyState({ onNew }: { onNew: () => void }) {
  return (
    <Card>
      <CardContent className="flex flex-col items-center justify-center gap-3 py-12 text-center">
        <div className="flex size-12 items-center justify-center rounded-full bg-muted">
          <Sparkles className="size-5 text-muted-foreground" />
        </div>
        <div className="space-y-1">
          <p className="text-sm font-medium">No meetings analyzed yet</p>
          <p className="text-xs text-muted-foreground">
            Paste a transcript or drop a .txt / .docx / .pdf to get started.
          </p>
        </div>
        <Button size="sm" onClick={onNew}>
          Analyze first meeting
        </Button>
      </CardContent>
    </Card>
  );
}

function MeetingRow({
  meeting,
  onOpen,
}: {
  meeting: MeetingSummary;
  onOpen: () => void;
}) {
  return (
    <button
      onClick={onOpen}
      className="w-full text-left"
      aria-label={`Open meeting from ${meeting.meeting_date ?? "unknown date"}`}
    >
      <Card className="transition-colors hover:border-primary/50">
        <CardContent className="flex items-start gap-3 py-3">
          <div className="mt-0.5 flex size-9 items-center justify-center rounded-md bg-muted">
            <CalendarDays className="size-4 text-muted-foreground" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <p className="text-sm font-medium">
                {meeting.meeting_date
                  ? new Date(meeting.meeting_date).toLocaleDateString()
                  : "Undated meeting"}
              </p>
              <Badge variant="secondary" className="text-[10px]">
                {meeting.action_item_count} action
                {meeting.action_item_count === 1 ? "" : "s"}
              </Badge>
              <Badge variant="outline" className="text-[10px]">
                {meeting.decision_count} decision
                {meeting.decision_count === 1 ? "" : "s"}
              </Badge>
            </div>
            <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">
              {meeting.summary ?? "(no summary)"}
            </p>
          </div>
        </CardContent>
      </Card>
    </button>
  );
}

function MeetingDetailView({
  detail,
  onGoToRisks,
}: {
  detail: MeetingDetail;
  onGoToRisks?: () => void;
}) {
  // Local checkbox toggle state — persistence is out of scope for M3, but the
  // UI needs to feel real. Keyed by the action item's index in the array.
  const [checked, setChecked] = React.useState<Record<number, boolean>>(() =>
    Object.fromEntries(
      detail.action_items.map((a: MeetingActionItem, i) => [i, a.done])
    )
  );

  return (
    <div className="space-y-6">
      <section className="space-y-2">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Summary
        </h4>
        {detail.summary ? (
          <div className="space-y-2 text-sm leading-relaxed">
            {detail.summary.split(/\n\n+/).map((p, i) => (
              <p key={i}>{p}</p>
            ))}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">(no summary)</p>
        )}
      </section>

      <section className="space-y-2">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Action items
        </h4>
        {detail.action_items.length === 0 ? (
          <p className="text-sm text-muted-foreground">None captured.</p>
        ) : (
          <div className="rounded-md border">
            <table className="w-full text-sm">
              <thead className="bg-muted/40 text-xs uppercase tracking-wide text-muted-foreground">
                <tr>
                  <th className="w-10 py-2 pl-3 text-left">Done</th>
                  <th className="py-2 text-left">Item</th>
                  <th className="py-2 text-left">Owner</th>
                  <th className="py-2 pr-3 text-left">Due</th>
                </tr>
              </thead>
              <tbody>
                {detail.action_items.map((a, i) => (
                  <tr key={i} className="border-t">
                    <td className="py-2 pl-3">
                      <input
                        type="checkbox"
                        checked={checked[i] ?? false}
                        onChange={(e) =>
                          setChecked((s) => ({ ...s, [i]: e.target.checked }))
                        }
                        aria-label={`Mark action item ${i + 1} done`}
                        className="size-4 cursor-pointer"
                      />
                    </td>
                    <td
                      className={cn(
                        "py-2 pr-2",
                        checked[i] ? "text-muted-foreground line-through" : ""
                      )}
                    >
                      {a.text || "(untitled)"}
                    </td>
                    <td className="py-2 pr-2 text-muted-foreground">
                      {a.owner || "—"}
                    </td>
                    <td className="py-2 pr-3 text-muted-foreground">
                      {a.due_date || "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="space-y-2">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Decisions
        </h4>
        {detail.decisions.length === 0 ? (
          <p className="text-sm text-muted-foreground">None captured.</p>
        ) : (
          <ul className="space-y-2">
            {detail.decisions.map((d, i) => (
              <li key={i} className="rounded-md border p-3 text-sm">
                <p>{d.text}</p>
                {d.made_by ? (
                  <p className="mt-1 text-xs text-muted-foreground">
                    Decided by {d.made_by}
                  </p>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>

      {onGoToRisks ? (
        <section className="space-y-2">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Risks surfaced
          </h4>
          <p className="text-sm text-muted-foreground">
            Any risks the LLM raised were saved to this project's risk log.
          </p>
          <Button
            variant="outline"
            size="sm"
            className="gap-1.5"
            onClick={onGoToRisks}
          >
            <CheckCircle2 className="size-4" /> Open Risks tab
          </Button>
        </section>
      ) : null}
    </div>
  );
}

function NewMeetingDialog({
  open,
  onOpenChange,
  onSubmit,
  analyzing,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onSubmit: (opts: {
    transcriptText?: string;
    file?: File;
    meetingDate?: string;
  }) => Promise<void> | void;
  analyzing: boolean;
}) {
  const [meetingDate, setMeetingDate] = React.useState<string>(
    () => new Date().toISOString().slice(0, 10)
  );
  const [transcript, setTranscript] = React.useState("");
  const [file, setFile] = React.useState<File | null>(null);
  const [dragOver, setDragOver] = React.useState(false);
  const inputRef = React.useRef<HTMLInputElement>(null);

  React.useEffect(() => {
    if (!open) {
      // Reset when the dialog closes so the next open is fresh.
      setTranscript("");
      setFile(null);
      setDragOver(false);
    }
  }, [open]);

  const canSubmit = !analyzing && (transcript.trim().length > 0 || file !== null);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Analyze a meeting</DialogTitle>
          <DialogDescription>
            Paste a transcript or drop a .txt / .docx / .pdf. Claude Sonnet 4.6
            extracts the summary, action items, decisions, and any risks.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="meeting-date">Meeting date</Label>
            <Input
              id="meeting-date"
              type="date"
              value={meetingDate}
              onChange={(e) => setMeetingDate(e.target.value)}
              disabled={analyzing}
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="transcript">Transcript</Label>
            <textarea
              id="transcript"
              value={transcript}
              onChange={(e) => {
                setTranscript(e.target.value);
                if (file) setFile(null);
              }}
              disabled={analyzing || file !== null}
              placeholder="Paste transcript here…"
              rows={6}
              className="w-full rounded-md border bg-transparent px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
            />
          </div>

          <div className="space-y-1.5">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Or drop a file
            </p>
            <div
              onDragOver={(e) => {
                e.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragOver(false);
                if (analyzing) return;
                const f = e.dataTransfer.files?.[0];
                if (f) {
                  setFile(f);
                  setTranscript("");
                }
              }}
              className={cn(
                "flex items-center justify-between gap-3 rounded-lg border-2 border-dashed p-3 text-sm transition-colors",
                dragOver
                  ? "border-primary bg-primary/5"
                  : "border-muted-foreground/25"
              )}
            >
              <div className="flex items-center gap-2 text-muted-foreground">
                {file ? (
                  <>
                    <FileText className="size-4" />
                    <span className="truncate">{file.name}</span>
                  </>
                ) : (
                  <>
                    <Upload className="size-4" />
                    <span>.txt · .docx · .pdf</span>
                  </>
                )}
              </div>
              <Button
                size="sm"
                variant="outline"
                type="button"
                onClick={() => inputRef.current?.click()}
                disabled={analyzing}
              >
                {file ? "Change" : "Choose"}
              </Button>
              <input
                ref={inputRef}
                type="file"
                accept={ACCEPT}
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) {
                    setFile(f);
                    setTranscript("");
                  }
                  e.target.value = "";
                }}
              />
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={analyzing}
          >
            Cancel
          </Button>
          <Button
            onClick={() =>
              void onSubmit({
                transcriptText: file ? undefined : transcript,
                file: file ?? undefined,
                meetingDate: meetingDate || undefined,
              })
            }
            disabled={!canSubmit}
            className="gap-1.5"
          >
            {analyzing ? (
              <>
                <Loader2 className="size-4 animate-spin" /> Analyzing…
              </>
            ) : (
              <>
                <Sparkles className="size-4" /> Analyze
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
