"use client";

import * as React from "react";
import { useAuth } from "@clerk/nextjs";
import { toast } from "sonner";
import { Upload, Eye, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import {
  uploadDocument,
  getDocumentContent,
  ApiError,
  type ProjectDocument,
  type DocumentStatus,
} from "@/lib/api";

interface UploadState {
  filename: string;
  fraction: number; // 0..1
}

export function DocumentsPanel({
  projectId,
  documents,
  onChanged,
}: {
  projectId: string;
  documents: ProjectDocument[];
  onChanged: () => void | Promise<void>;
}) {
  const { getToken } = useAuth();
  const inputRef = React.useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = React.useState(false);
  const [uploading, setUploading] = React.useState<UploadState | null>(null);

  async function upload(file: File) {
    setUploading({ filename: file.name, fraction: 0 });
    try {
      const token = await getToken();
      await uploadDocument(
        {
          projectId,
          file,
          onProgress: (frac) =>
            setUploading((prev) =>
              prev ? { ...prev, fraction: frac } : prev
            ),
        },
        { token }
      );
      toast.success(`Uploaded ${file.name}`);
      await onChanged();
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? `API ${err.status}: ${err.body ?? err.message}`
          : err instanceof Error
            ? err.message
            : "Upload failed";
      toast.error(msg);
    } finally {
      setUploading(null);
    }
  }

  function onSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) void upload(file);
    e.target.value = "";
  }

  function onDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file) void upload(file);
  }

  return (
    <div className="space-y-6">
      {/* Dropzone */}
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        className={cn(
          "flex flex-col items-center gap-4 rounded-2xl border-2 border-dashed p-6 transition-colors sm:flex-row sm:items-center",
          dragOver
            ? "border-primary bg-primary/5"
            : "border-muted-foreground/30"
        )}
      >
        <div className="flex size-12 shrink-0 items-center justify-center rounded-xl bg-primary/15 text-primary">
          <Upload className="size-5" />
        </div>
        <div className="min-w-0 flex-1 text-center sm:text-left">
          <p className="font-display text-base font-bold text-foreground">
            Drop documents to analyze
          </p>
          <p className="text-sm text-muted-foreground">
            Schedules, cost reports, RFIs, meeting minutes — PDF, XER, XLSX,
            DOCX up to 200MB
          </p>
        </div>
        <Button
          onClick={() => inputRef.current?.click()}
          disabled={uploading !== null}
          className="shrink-0"
        >
          {uploading ? "Uploading…" : "Browse files"}
        </Button>
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf,.pdf,.docx,.xlsx"
          className="hidden"
          onChange={onSelect}
        />
      </div>

      {uploading ? (
        <Card className="rounded-2xl border bg-card">
          <CardContent className="space-y-2 pt-6">
            <div className="flex items-center justify-between text-sm">
              <span className="truncate font-medium">{uploading.filename}</span>
              <span className="tabular-nums text-muted-foreground">
                {Math.round(uploading.fraction * 100)}%
              </span>
            </div>
            <Progress value={uploading.fraction * 100} />
          </CardContent>
        </Card>
      ) : null}

      {/* Documents table */}
      {documents.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No documents yet. Upload one above.
        </p>
      ) : (
        <div className="overflow-hidden rounded-2xl border bg-card">
          <div className="overflow-x-auto">
            <div className="min-w-[640px]">
              {/* Header */}
              <div className="grid grid-cols-[1fr_130px_90px_130px_90px] items-center gap-2 bg-secondary px-4 py-2.5 text-[11px] font-bold uppercase tracking-wide text-muted-foreground">
                <div>Document</div>
                <div>Type</div>
                <div className="text-center">Pages</div>
                <div>Analyzed</div>
                <div />
              </div>
              {documents.map((doc) => (
                <DocumentRow key={doc.id} doc={doc} projectId={projectId} />
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

const EXT_STYLES: Record<string, string> = {
  PDF: "bg-[#F65563]/15 text-[#F65563]",
  DOCX: "bg-[#3B93F0]/15 text-[#3B93F0]",
  DOC: "bg-[#3B93F0]/15 text-[#3B93F0]",
  XLSX: "bg-[#35C97F]/15 text-[#35C97F]",
  XLS: "bg-[#35C97F]/15 text-[#35C97F]",
};

const TYPE_LABELS: Record<string, string> = {
  PDF: "PDF",
  DOCX: "Meeting notes",
  DOC: "Meeting notes",
  XLSX: "Cost report",
  XLS: "Cost report",
  XER: "Schedule",
};

function fileExt(filename: string): string {
  const parts = filename.split(".");
  if (parts.length < 2) return "DOC";
  return parts[parts.length - 1]!.toUpperCase();
}

function DocumentRow({
  doc,
  projectId,
}: {
  doc: ProjectDocument;
  projectId: string;
}) {
  const { getToken } = useAuth();
  const [open, setOpen] = React.useState(false);
  const [loading, setLoading] = React.useState(false);
  const [text, setText] = React.useState<string | null>(null);
  const canView = doc.status === "ready";

  const ext = fileExt(doc.filename);
  const badgeStyle = EXT_STYLES[ext] ?? "bg-muted text-muted-foreground";
  const typeLabel = TYPE_LABELS[ext] ?? ext;

  async function view() {
    setOpen(true);
    if (text !== null) return;
    setLoading(true);
    try {
      const token = await getToken();
      const content = await getDocumentContent(projectId, doc.id, { token });
      setText(content.text || "(no extractable text in this document)");
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? `Could not load document (${err.status})`
          : "Could not load document";
      setText(msg);
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <div className="grid grid-cols-[1fr_130px_90px_130px_90px] items-center gap-2 border-b border-border px-4 py-3 last:border-b-0">
        {/* Document */}
        <div className="flex min-w-0 items-center gap-3">
          <div
            className={cn(
              "flex size-[34px] shrink-0 items-center justify-center rounded-lg text-[10px] font-bold",
              badgeStyle
            )}
          >
            {ext.slice(0, 4)}
          </div>
          <div className="min-w-0">
            <p className="truncate text-sm font-medium text-foreground">
              {doc.filename}
            </p>
            <p className="truncate text-xs text-muted-foreground">
              {formatBytes(doc.bytes)}
            </p>
          </div>
        </div>

        {/* Type */}
        <div className="truncate text-sm text-muted-foreground">{typeLabel}</div>

        {/* Pages */}
        <div className="text-center text-sm tabular-nums text-muted-foreground">
          —
        </div>

        {/* Analyzed */}
        <div className="text-sm text-muted-foreground">
          {new Date(doc.uploaded_at).toLocaleDateString(undefined, {
            month: "short",
            day: "numeric",
            year: "numeric",
          })}
        </div>

        {/* View / status */}
        <div className="flex justify-end">
          {canView ? (
            <Button
              variant="outline"
              size="sm"
              onClick={view}
              className="gap-1.5"
            >
              <Eye className="size-3.5" /> View
            </Button>
          ) : (
            <StatusBadge status={doc.status} />
          )}
        </div>
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-h-[85vh] max-w-3xl overflow-hidden">
          <DialogHeader>
            <DialogTitle className="truncate">{doc.filename}</DialogTitle>
            <DialogDescription>
              Extracted text, reconstructed from the indexed document.
            </DialogDescription>
          </DialogHeader>
          <div className="max-h-[65vh] overflow-y-auto rounded-lg border bg-muted/30 p-4">
            {loading ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="size-4 animate-spin" /> Loading document…
              </div>
            ) : (
              <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed text-foreground">
                {text}
              </pre>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

function StatusBadge({ status }: { status: DocumentStatus }) {
  if (status === "ready") {
    return (
      <Badge variant="secondary" className="gap-1">
        Ready
      </Badge>
    );
  }
  if (status === "failed") {
    return (
      <Badge variant="destructive" className="gap-1">
        Failed
      </Badge>
    );
  }
  return (
    <Badge variant="outline" className="gap-1">
      {status === "uploaded"
        ? "Queued"
        : status === "extracting"
          ? "Extracting"
          : "Embedding"}
    </Badge>
  );
}

function formatBytes(bytes?: number): string {
  if (!bytes) return "unknown size";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
