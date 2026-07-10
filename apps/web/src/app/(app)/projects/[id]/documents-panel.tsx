"use client";

import * as React from "react";
import { useAuth } from "@clerk/nextjs";
import { toast } from "sonner";
import { FileText, Upload, CheckCircle2, Clock, XCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import {
  uploadDocument,
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
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        className={cn(
          "flex flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed p-8 text-center transition-colors",
          dragOver
            ? "border-primary bg-primary/5"
            : "border-muted-foreground/25"
        )}
      >
        <div className="flex size-12 items-center justify-center rounded-full bg-muted">
          <Upload className="size-5 text-muted-foreground" />
        </div>
        <div className="space-y-1">
          <p className="text-sm font-medium">
            Drop a PDF here, or click to browse
          </p>
          <p className="text-xs text-muted-foreground">
            Schedules, budgets, RFI logs, meeting notes — anything project-related.
          </p>
        </div>
        <Button
          size="sm"
          onClick={() => inputRef.current?.click()}
          disabled={uploading !== null}
        >
          {uploading ? "Uploading…" : "Upload PDF"}
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
        <Card>
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

      <div className="space-y-2">
        {documents.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No documents yet. Upload one above.
          </p>
        ) : (
          documents.map((doc) => <DocumentRow key={doc.id} doc={doc} />)
        )}
      </div>
    </div>
  );
}

function DocumentRow({ doc }: { doc: ProjectDocument }) {
  return (
    <Card>
      <CardContent className="flex items-center gap-3 py-3">
        <FileText className="size-5 text-muted-foreground" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">{doc.filename}</p>
          <p className="text-xs text-muted-foreground">
            {formatBytes(doc.bytes)} · uploaded{" "}
            {new Date(doc.uploaded_at).toLocaleString()}
          </p>
        </div>
        <StatusBadge status={doc.status} />
      </CardContent>
    </Card>
  );
}

function StatusBadge({ status }: { status: DocumentStatus }) {
  if (status === "ready") {
    return (
      <Badge variant="secondary" className="gap-1">
        <CheckCircle2 className="size-3" /> Ready
      </Badge>
    );
  }
  if (status === "failed") {
    return (
      <Badge variant="destructive" className="gap-1">
        <XCircle className="size-3" /> Failed
      </Badge>
    );
  }
  return (
    <Badge variant="outline" className="gap-1">
      <Clock className="size-3" />
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
