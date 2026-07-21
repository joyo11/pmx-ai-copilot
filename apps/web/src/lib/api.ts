/**
 * PMX AI API client.
 *
 * Small typed wrapper around the FastAPI backend. Every request carries a
 * fresh Clerk JWT via `Authorization: Bearer …`.
 *
 * Callers on the client pass the token they got from `useAuth().getToken()`.
 * Server components should call `auth().getToken()` (async in Next 15+) and
 * pass the resulting string in the same way. Keeping token acquisition at the
 * call site (rather than inside this module) means this file has zero Clerk
 * dependency and stays trivially testable.
 */

export type ProjectSector =
  | "healthcare"
  | "infrastructure"
  | "transportation"
  | "education"
  | "commercial"
  | "other";

export type ProjectStatus = "active" | "on_hold" | "closed" | "archived";

export interface Project {
  id: string;
  name: string;
  client: string | null;
  sector: ProjectSector | null;
  status: ProjectStatus;
  health_score: number | null;
  document_count?: number;
  planned_end_date?: string | null;
  forecast_end_date?: string | null;
  budget_total_cents?: number | null;
  budget_spent_cents?: number | null;
  created_at: string;
  updated_at?: string;
}

export interface CreateProjectInput {
  name: string;
  client: string;
  sector: ProjectSector;
}

export type DocumentStatus =
  | "uploaded"
  | "extracting"
  | "embedding"
  | "ready"
  | "failed";

export interface ProjectDocument {
  id: string;
  project_id: string;
  filename: string;
  status: DocumentStatus;
  bytes?: number;
  uploaded_at: string;
  processed_at?: string | null;
  error?: string | null;
}

export interface Citation {
  document_id: string;
  document_filename?: string;
  chunk_id?: string;
  page?: number | null;
}

export type ChatEvent =
  | { type: "token"; text: string }
  | { type: "citation"; citation: Citation }
  | { type: "tool_call"; name: string; arguments?: unknown }
  | { type: "done"; session_id?: string }
  | { type: "error"; message: string };

// ---------------------------------------------------------------------------
// Internals
// ---------------------------------------------------------------------------

/** Signalled by callers so their error UI can render friendly copy instead of crashing. */
export class ApiNotConfiguredError extends Error {
  constructor() {
    super(
      "PMX API URL is not configured. Set NEXT_PUBLIC_API_URL in Vercel env."
    );
    this.name = "ApiNotConfiguredError";
  }
}

// Deployed backend on Render. Used when NEXT_PUBLIC_API_URL isn't set at build
// time (e.g. the Vercel env var is empty), so production never falls back to a
// dead host. Local dev overrides this via .env.local (NEXT_PUBLIC_API_URL).
const DEFAULT_API_URL = "https://pmx-api-l893.onrender.com";

function apiBase(): string {
  const configured =
    typeof process !== "undefined"
      ? process.env.NEXT_PUBLIC_API_URL
      : undefined;
  const url = configured && configured.trim() ? configured.trim() : DEFAULT_API_URL;
  return url.replace(/\/+$/, "");
}

interface RequestOptions {
  token: string | null | undefined;
  signal?: AbortSignal;
}

async function apiFetch(
  path: string,
  init: RequestInit,
  { token, signal }: RequestOptions
): Promise<Response> {
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (!headers.has("Accept")) headers.set("Accept", "application/json");

  const res = await fetch(`${apiBase()}${path}`, {
    ...init,
    headers,
    signal,
    // Never let the browser (or Next) cache mutating or user-scoped GETs.
    cache: "no-store",
  });

  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new ApiError(res.status, res.statusText, body || undefined);
  }
  return res;
}

export class ApiError extends Error {
  status: number;
  body?: string;
  constructor(status: number, statusText: string, body?: string) {
    super(`API ${status} ${statusText}${body ? `: ${body}` : ""}`);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

// ---------------------------------------------------------------------------
// Projects
// ---------------------------------------------------------------------------

export async function listProjects(opts: RequestOptions): Promise<Project[]> {
  const res = await apiFetch("/v1/projects", { method: "GET" }, opts);
  return (await res.json()) as Project[];
}

export async function getProject(
  id: string,
  opts: RequestOptions
): Promise<Project> {
  const res = await apiFetch(`/v1/projects/${id}`, { method: "GET" }, opts);
  return (await res.json()) as Project;
}

export async function createProject(
  input: CreateProjectInput,
  opts: RequestOptions
): Promise<Project> {
  const res = await apiFetch(
    "/v1/projects",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    },
    opts
  );
  return (await res.json()) as Project;
}

// ---------------------------------------------------------------------------
// Documents
// ---------------------------------------------------------------------------

export async function listDocuments(
  projectId: string,
  opts: RequestOptions
): Promise<ProjectDocument[]> {
  const res = await apiFetch(
    `/v1/projects/${projectId}/documents`,
    { method: "GET" },
    opts
  );
  return (await res.json()) as ProjectDocument[];
}

export interface DocumentContent {
  document_id: string;
  filename: string;
  kind: string;
  pages: number;
  text: string;
}

export async function getDocumentContent(
  projectId: string,
  documentId: string,
  opts: RequestOptions
): Promise<DocumentContent> {
  const res = await apiFetch(
    `/v1/projects/${projectId}/documents/${documentId}/content`,
    { method: "GET" },
    opts
  );
  return (await res.json()) as DocumentContent;
}

export interface UploadDocumentInput {
  projectId: string;
  file: File;
  onProgress?: (fractionComplete: number) => void;
}

/**
 * Multipart upload with progress. `fetch()` doesn't expose upload progress
 * yet in browsers, so this uses XHR under the hood. It's the only place in
 * the client that touches XHR; every other call uses fetch.
 */
export function uploadDocument(
  input: UploadDocumentInput,
  { token }: RequestOptions
): Promise<{ document_id: string; status: DocumentStatus }> {
  const { projectId, file, onProgress } = input;
  const url = `${apiBase()}/v1/projects/${projectId}/documents`;
  const fd = new FormData();
  fd.append("file", file, file.name);

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", url, true);
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    xhr.setRequestHeader("Accept", "application/json");

    xhr.upload.onprogress = (e) => {
      if (!onProgress || !e.lengthComputable) return;
      onProgress(e.loaded / e.total);
    };
    xhr.onerror = () =>
      reject(new ApiError(0, "network error", "Upload failed"));
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const parsed = JSON.parse(xhr.responseText);
          resolve(parsed);
        } catch (err) {
          reject(new ApiError(xhr.status, "invalid json", String(err)));
        }
      } else {
        reject(
          new ApiError(xhr.status, xhr.statusText, xhr.responseText || undefined)
        );
      }
    };
    xhr.send(fd);
  });
}

// ---------------------------------------------------------------------------
// Risks
// ---------------------------------------------------------------------------

export type RiskCategory =
  | "schedule"
  | "budget"
  | "operational"
  | "communication"
  | "compliance";

export type RiskStatus = "open" | "acknowledged" | "mitigated" | "resolved";

/** Severity is a 1..5 integer; higher = worse. */
export type RiskSeverity = 1 | 2 | 3 | 4 | 5;

export interface RiskSummary {
  id: string;
  project_id: string;
  title: string;
  category: RiskCategory;
  severity: RiskSeverity;
  likelihood: number; // 0..1
  business_impact?: string | null;
  confidence?: number | null; // 0..1
  status: RiskStatus;
  created_at: string;
  updated_at?: string | null;
}

export interface RiskDetail extends RiskSummary {
  description: string;
  recommended_action?: string | null;
  citations: Citation[];
}

export interface ListRisksFilters {
  category?: RiskCategory;
  severity_gte?: number;
  status?: RiskStatus;
}

function toQuery(params: Record<string, string | number | undefined>): string {
  const entries = Object.entries(params).filter(
    ([, v]) => v !== undefined && v !== null && v !== ""
  );
  if (entries.length === 0) return "";
  const usp = new URLSearchParams();
  for (const [k, v] of entries) usp.set(k, String(v));
  return `?${usp.toString()}`;
}

export async function listRisks(
  projectId: string,
  filters: ListRisksFilters | undefined,
  opts: RequestOptions
): Promise<RiskSummary[]> {
  const qs = toQuery({
    category: filters?.category,
    severity_gte: filters?.severity_gte,
    status: filters?.status,
  });
  const res = await apiFetch(
    `/v1/projects/${projectId}/risks${qs}`,
    { method: "GET" },
    opts
  );
  return (await res.json()) as RiskSummary[];
}

export async function getRisk(
  riskId: string,
  opts: RequestOptions
): Promise<RiskDetail> {
  const res = await apiFetch(`/v1/risks/${riskId}`, { method: "GET" }, opts);
  return (await res.json()) as RiskDetail;
}

export async function updateRiskStatus(
  riskId: string,
  status: Exclude<RiskStatus, "open">,
  opts: RequestOptions
): Promise<RiskSummary> {
  const res = await apiFetch(
    `/v1/risks/${riskId}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    },
    opts
  );
  return (await res.json()) as RiskSummary;
}

export interface ScanResponse {
  scan_id?: string;
  status?: string;
}

export async function scanProjectRisks(
  projectId: string,
  opts: RequestOptions
): Promise<ScanResponse> {
  const res = await apiFetch(
    `/v1/projects/${projectId}/risks/scan`,
    { method: "POST" },
    opts
  );
  // Some APIs return 202 Accepted with no body — tolerate that.
  const text = await res.text();
  if (!text) return {};
  try {
    return JSON.parse(text) as ScanResponse;
  } catch {
    return {};
  }
}

// ---------------------------------------------------------------------------
// Health
// ---------------------------------------------------------------------------

export interface HealthFactor {
  key: string;
  label?: string;
  weight: number; // 0..1
  score: number; // 0..100
}

export interface HealthSnapshot {
  score: number; // 0..100
  factors: HealthFactor[];
  reasoning?: string | null;
  computed_at: string;
}

// The API stores `factors` as a JSONB dict keyed by factor name
// ({budget_variance: {label, value, sub_score, weight, detail}, ...}), but the
// UI expects an array of {key, label, weight, score}. Normalize here so every
// consumer gets the array shape (and tolerate the array shape too).
function normalizeHealth(raw: unknown): HealthSnapshot {
  const snap = (raw ?? {}) as Record<string, unknown>;
  const f = snap.factors;
  let factors: HealthFactor[] = [];
  if (Array.isArray(f)) {
    factors = f as HealthFactor[];
  } else if (f && typeof f === "object") {
    factors = Object.entries(f as Record<string, Record<string, unknown>>).map(
      ([key, v]) => ({
        key,
        label: typeof v?.label === "string" ? v.label : undefined,
        weight: typeof v?.weight === "number" ? v.weight : 0,
        score:
          typeof v?.sub_score === "number"
            ? Math.round(v.sub_score * 100)
            : typeof v?.score === "number"
              ? v.score
              : 0,
      })
    );
  }
  return { ...(snap as unknown as HealthSnapshot), factors };
}

export async function getHealth(
  projectId: string,
  opts: RequestOptions
): Promise<HealthSnapshot> {
  const res = await apiFetch(
    `/v1/projects/${projectId}/health`,
    { method: "GET" },
    opts
  );
  return normalizeHealth(await res.json());
}

export async function recomputeHealth(
  projectId: string,
  opts: RequestOptions
): Promise<HealthSnapshot> {
  const res = await apiFetch(
    `/v1/projects/${projectId}/health/recompute`,
    { method: "POST" },
    opts
  );
  return normalizeHealth(await res.json());
}

export async function getHealthHistory(
  projectId: string,
  opts: RequestOptions
): Promise<HealthSnapshot[]> {
  const res = await apiFetch(
    `/v1/projects/${projectId}/health/history`,
    { method: "GET" },
    opts
  );
  const data = (await res.json()) as unknown[];
  return Array.isArray(data) ? data.map(normalizeHealth) : [];
}

// ---------------------------------------------------------------------------
// Meetings (M3)
// ---------------------------------------------------------------------------

export interface MeetingActionItem {
  text: string;
  owner: string;
  due_date: string;
  done: boolean;
}

export interface MeetingDecision {
  text: string;
  made_by: string;
}

export interface MeetingSummary {
  id: string;
  project_id: string;
  meeting_date: string | null;
  summary: string | null;
  action_item_count: number;
  decision_count: number;
}

export interface MeetingDetail {
  id: string;
  project_id: string;
  meeting_date: string | null;
  summary: string | null;
  action_items: MeetingActionItem[];
  decisions: MeetingDecision[];
}

export interface AnalyzeMeetingResponse {
  meeting_id: string;
  summary: string;
  action_items: MeetingActionItem[];
  decisions: MeetingDecision[];
  risks_created: number;
}

export interface AnalyzeMeetingInput {
  projectId: string;
  meetingDate?: string; // YYYY-MM-DD
  transcriptText?: string;
  file?: File;
}

/**
 * Analyze a meeting transcript. Chooses JSON or multipart based on whether
 * `file` is set. The API accepts either at the same URL.
 */
export async function analyzeMeeting(
  input: AnalyzeMeetingInput,
  opts: RequestOptions
): Promise<AnalyzeMeetingResponse> {
  const { projectId, meetingDate, transcriptText, file } = input;
  const path = `/v1/projects/${projectId}/meetings/analyze`;

  if (file) {
    const fd = new FormData();
    fd.append("file", file, file.name);
    if (meetingDate) fd.append("meeting_date", meetingDate);
    const res = await apiFetch(path, { method: "POST", body: fd }, opts);
    return (await res.json()) as AnalyzeMeetingResponse;
  }

  const res = await apiFetch(
    path,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        transcript_text: transcriptText ?? "",
        meeting_date: meetingDate,
      }),
    },
    opts
  );
  return (await res.json()) as AnalyzeMeetingResponse;
}

export async function listMeetings(
  projectId: string,
  opts: RequestOptions
): Promise<MeetingSummary[]> {
  const res = await apiFetch(
    `/v1/projects/${projectId}/meetings`,
    { method: "GET" },
    opts
  );
  return (await res.json()) as MeetingSummary[];
}

export async function getMeeting(
  meetingId: string,
  opts: RequestOptions
): Promise<MeetingDetail> {
  const res = await apiFetch(
    `/v1/meetings/${meetingId}`,
    { method: "GET" },
    opts
  );
  return (await res.json()) as MeetingDetail;
}

// ---------------------------------------------------------------------------
// Chat (SSE-over-POST)
// ---------------------------------------------------------------------------

export interface SendChatInput {
  projectId: string;
  message: string;
  sessionId?: string;
}

/**
 * Streams assistant events for a chat message. Because SSE-over-EventSource
 * is GET-only, we roll our own reader on top of `fetch` + `ReadableStream`.
 *
 * The server writes the standard SSE format:
 *   event: <name>\n
 *   data: <json>\n\n
 *
 * We yield one `ChatEvent` per parsed frame.
 */
export async function* sendChatMessage(
  input: SendChatInput,
  { token, signal }: RequestOptions
): AsyncGenerator<ChatEvent, void, void> {
  const { projectId, message, sessionId } = input;
  const res = await fetch(`${apiBase()}/v1/projects/${projectId}/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ message, session_id: sessionId }),
    signal,
    cache: "no-store",
  });

  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new ApiError(res.status, res.statusText, body || undefined);
  }
  if (!res.body) {
    throw new ApiError(0, "no body", "Server returned an empty stream");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // Frames are terminated by a blank line.
      let sepIdx: number;
      while ((sepIdx = indexOfFrameSeparator(buffer)) !== -1) {
        const frame = buffer.slice(0, sepIdx);
        buffer = buffer.slice(sepIdx).replace(/^(\r?\n){2}/, "");
        const evt = parseFrame(frame);
        if (evt) yield evt;
      }
    }
    // Flush any trailing frame with no terminating blank line.
    const tail = buffer.trim();
    if (tail) {
      const evt = parseFrame(tail);
      if (evt) yield evt;
    }
  } finally {
    reader.releaseLock();
  }
}

function indexOfFrameSeparator(s: string): number {
  const a = s.indexOf("\n\n");
  const b = s.indexOf("\r\n\r\n");
  if (a === -1) return b;
  if (b === -1) return a;
  return Math.min(a, b);
}

function parseFrame(frame: string): ChatEvent | null {
  let eventName = "message";
  const dataLines: string[] = [];

  for (const rawLine of frame.split(/\r?\n/)) {
    if (!rawLine || rawLine.startsWith(":")) continue; // comment or empty
    const colonIdx = rawLine.indexOf(":");
    const field = colonIdx === -1 ? rawLine : rawLine.slice(0, colonIdx);
    const value =
      colonIdx === -1
        ? ""
        : rawLine.slice(colonIdx + 1).replace(/^ /, "");
    if (field === "event") eventName = value;
    else if (field === "data") dataLines.push(value);
  }

  if (dataLines.length === 0 && eventName === "message") return null;
  const dataStr = dataLines.join("\n");

  let payload: unknown = {};
  if (dataStr) {
    try {
      payload = JSON.parse(dataStr);
    } catch {
      // Fall back to raw text for `token` frames that send plain strings.
      payload = { text: dataStr };
    }
  }
  const obj = (payload ?? {}) as Record<string, unknown>;

  switch (eventName) {
    case "token":
      return { type: "token", text: String(obj.text ?? "") };
    case "citation":
      return {
        type: "citation",
        citation: (obj.citation ?? obj) as Citation,
      };
    case "tool_call":
      return {
        type: "tool_call",
        name: String(obj.name ?? ""),
        arguments: obj.arguments,
      };
    case "done":
      return {
        type: "done",
        session_id:
          typeof obj.session_id === "string" ? obj.session_id : undefined,
      };
    case "error":
      return {
        type: "error",
        message: String(obj.message ?? "Unknown error"),
      };
    default:
      return null;
  }
}
