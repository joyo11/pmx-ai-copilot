"use client";

import * as React from "react";
import { FileText } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { Citation } from "@/lib/api";

/**
 * Shared citation chip used by the chat panel and the risk detail sheet.
 *
 * `inline` toggles the visual density: inline citations sit next to an answer
 * bubble and get the lighter `outline` treatment; standalone chips (e.g. in a
 * sources list) render as filled `secondary` badges.
 */
export function CitationChip({
  citation,
  inline,
}: {
  citation: Citation;
  inline?: boolean;
}) {
  const label = citation.document_filename ?? citation.document_id;
  const page =
    typeof citation.page === "number" ? `p.${citation.page}` : null;
  return (
    <Badge
      variant={inline ? "outline" : "secondary"}
      className="gap-1 font-normal"
    >
      <FileText className="size-3" />
      <span className="max-w-[180px] truncate">{label}</span>
      {page ? (
        <span className="text-muted-foreground tabular-nums">{page}</span>
      ) : null}
    </Badge>
  );
}

/** Stable dedupe/react key for a citation triple. */
export function citationKey(c: Citation): string {
  return `${c.document_id}:${c.chunk_id ?? ""}:${c.page ?? ""}`;
}

export function dedupeCitations(cs: Citation[]): Citation[] {
  const seen = new Set<string>();
  const out: Citation[] = [];
  for (const c of cs) {
    const k = citationKey(c);
    if (seen.has(k)) continue;
    seen.add(k);
    out.push(c);
  }
  return out;
}
