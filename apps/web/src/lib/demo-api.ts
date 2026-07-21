/**
 * Public demo API client — NO auth token.
 *
 * Hits the anonymous /v1/demo/* endpoints on the FastAPI backend so the
 * public /demo page can render the seeded Northshore project without a Clerk
 * session. Mirrors apiBase() from lib/api.ts but sends no Authorization header.
 */

const DEFAULT_API_URL = "https://pmx-api-l893.onrender.com";

function apiBase(): string {
  const configured =
    typeof process !== "undefined"
      ? process.env.NEXT_PUBLIC_API_URL
      : undefined;
  const url =
    configured && configured.trim() ? configured.trim() : DEFAULT_API_URL;
  return url.replace(/\/+$/, "");
}

export interface DemoProject {
  name: string;
  client: string | null;
  sector: string | null;
  health_score: number | null;
  planned_end_date: string | null;
  forecast_end_date: string | null;
  budget_total_cents: number | null;
  budget_spent_cents: number | null;
}

export interface DemoHealthFactor {
  key: string;
  label: string;
  weight: number;
  score: number;
}

export interface DemoHealth {
  score: number;
  factors: DemoHealthFactor[];
}

export interface DemoRiskCitation {
  document_id?: string;
  chunk_id?: string;
  page?: number | null;
  [k: string]: unknown;
}

export interface DemoRisk {
  id: string;
  category: string;
  title: string;
  description: string;
  severity: number;
  likelihood: number | null;
  confidence: number | null;
  status: string;
  business_impact: string | null;
  recommended_action: string | null;
  citations: DemoRiskCitation[];
}

export interface DemoDocument {
  id: string;
  filename: string;
  kind: string;
  status: string;
}

export interface DemoBundle {
  project: DemoProject | null;
  health: DemoHealth | null;
  risks: DemoRisk[];
  documents: DemoDocument[];
}

export interface DemoChatCitation {
  document_id: string;
  chunk_id: string;
  page: number | null;
}

export interface DemoChatResponse {
  answer: string;
  citations: DemoChatCitation[];
}

export async function getDemoBundle(
  signal?: AbortSignal
): Promise<DemoBundle> {
  const res = await fetch(`${apiBase()}/v1/demo/bundle`, {
    method: "GET",
    headers: { Accept: "application/json" },
    cache: "no-store",
    signal,
  });
  if (!res.ok) {
    throw new Error(`Demo bundle failed: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as DemoBundle;
}

export async function postDemoChat(
  message: string,
  signal?: AbortSignal
): Promise<DemoChatResponse> {
  const res = await fetch(`${apiBase()}/v1/demo/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify({ message }),
    cache: "no-store",
    signal,
  });
  if (!res.ok) {
    throw new Error(`Demo chat failed: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as DemoChatResponse;
}
