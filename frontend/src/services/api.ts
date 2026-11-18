// ============================================================
// Tayf Studio - unified HTTP client (zero mock data)
// ------------------------------------------------------------
// HONESTY RULE: every function here calls the REAL backend
// through the Vite dev proxy ('/api' -> http://127.0.0.1:8000).
// There is no fake data, no fake latency, no fake success.
// ============================================================

const API = "/api/v1";
const TIMEOUT_MS = 15_000;

// The access JWT lives in memory only (never localStorage): an XSS can at
// worst read a short-lived token. The refresh JWT is an HttpOnly cookie that
// JavaScript cannot read at all — the browser attaches it on refresh/logout.
let accessToken: string | null = null;

export function getToken(): string | null {
  return accessToken;
}

export function setToken(token: string | null): void {
  accessToken = token;
}

export function setSession(token: string): void {
  accessToken = token;
}

// Single-flight refresh: concurrent 401s share one /auth/refresh call.
let refreshInFlight: Promise<string | null> | null = null;

async function tryRefresh(): Promise<string | null> {
  if (!refreshInFlight) {
    refreshInFlight = request<TokenResponse>("/auth/refresh", {
      method: "POST",
      allowRefresh: false,
    })
      .then((data) => {
        setToken(data.access_token);
        return data.access_token;
      })
      .catch(() => {
        setToken(null);
        return null;
      })
      .finally(() => {
        refreshInFlight = null;
      });
  }
  return refreshInFlight;
}

async function request<T>(
  path: string,
  options: {
    method?: string;
    body?: unknown;
    token?: string | null;
    timeout?: number;
    allowRefresh?: boolean;
  } = {},
): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), options.timeout ?? TIMEOUT_MS);
  let response: Response;
  try {
    response = await fetch(API + path, {
      method: options.method ?? "GET",
      signal: controller.signal,
      credentials: "include", // sends the HttpOnly refresh cookie on /auth/*
      headers: {
        ...(options.body !== undefined ? { "Content-Type": "application/json" } : {}),
        ...(options.token ? { Authorization: `Bearer ${options.token}` } : {}),
      },
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new Error("انتهت المهلة - الخادم لا يستجيب (هل شُغِّل الخادم؟)");
    }
    throw new Error("فشل الاتصال بالشبكة - تحقق من أن الخادم يعمل");
  } finally {
    clearTimeout(timer);
  }

  // Expired access token -> rotate silently once, then retry the request.
  if (response.status === 401 && options.token && options.allowRefresh !== false) {
    const renewed = await tryRefresh();
    if (renewed) {
      return request<T>(path, { ...options, token: renewed, allowRefresh: false });
    }
  }

  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
      else if (Array.isArray(body.detail)) {
        const first = body.detail[0] as { msg?: string } | undefined;
        if (first?.msg) detail = first.msg;
      }
    } catch {
      /* non-JSON error body: keep the status line */
    }
    throw new Error(detail);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

// ---------- wire contracts ----------

export interface Health {
  status: string;
  service: string;
  environment: string;
  timestamp: string;
}

export interface UserOut {
  id: string;
  email: string;
  username: string;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: UserOut;
  balance: number;
}

export interface MeResponse {
  user: UserOut;
  balance: number;
}

export interface Project {
  id: string;
  name: string;
  description: string | null;
  owner_id: string;
  status: "draft" | "active" | "archived";
  created_at: string;
  updated_at: string;
  job_count: number;
}

export interface Scene {
  index: number;
  description: string;
  image_url: string | null;
  duration_seconds: number;
}

export type JobStatus =
  | "pending"
  | "processing"
  | "completed"
  | "failed"
  | "rejected"
  | "cancelled";

export interface Job {
  id: string;
  project_id: string;
  status: JobStatus;
  provider: string;
  model_version: string;
  simulated: boolean;
  prompt: string;
  num_scenes: number;
  aspect: string;
  style: string;
  error_message: string | null;
  rejection_reason: string | null;
  safety_category: string | null;
  progress: number;
  stage: string;
  output_url: string | null;
  thumbnail_url: string | null;
  video_size_bytes: number | null;
  duration_seconds: number | null;
  credits_charged: number;
  created_at: string;
  completed_at: string | null;
  scenes: Scene[];
}

export interface StreamTicket {
  job_id: string;
  ticket: string;
  expires_at: string;
  expires_in: number;
}

export interface JobProgressEvent {
  job_id: string;
  status: JobStatus;
  progress: number;
  stage: string;
  error_message: string | null;
  rejection_reason: string | null;
  output_url: string | null;
  thumbnail_url: string | null;
  completed_at: string | null;
}

export interface LedgerEntry {
  id: string;
  delta: number;
  balance_after: number;
  reason: string;
  job_id: string | null;
  created_at: string;
}

export interface Credits {
  balance: number;
  entries: LedgerEntry[];
}

export interface VersionInfo {
  service: string;
  version: string;
  api_prefix: string;
  environment: string;
  python_version: string;
  storage_backend: string;
  ai_provider: string;
  timestamp: string;
}

// ---------- endpoints ----------

export function checkHealth(): Promise<Health> {
  return request<Health>("/health", { timeout: 5000 });
}

export function fetchVersion(): Promise<VersionInfo> {
  return request<VersionInfo>("/version", { timeout: 5000 });
}

export function register(payload: {
  email: string;
  username: string;
  password: string;
}): Promise<TokenResponse> {
  return request<TokenResponse>("/auth/register", { method: "POST", body: payload });
}

export function login(payload: {
  username_or_email: string;
  password: string;
}): Promise<TokenResponse> {
  return request<TokenResponse>("/auth/login", { method: "POST", body: payload });
}

export function fetchMe(token: string): Promise<MeResponse> {
  return request<MeResponse>("/auth/me", { token });
}

export function fetchCredits(token: string): Promise<Credits> {
  return request<Credits>("/credits/me", { token });
}

export function listProjects(
  token: string,
  params: { include_archived?: boolean; limit?: number; offset?: number } = {},
): Promise<Project[]> {
  const query = new URLSearchParams();
  if (params.include_archived) query.set("include_archived", "true");
  if (params.limit !== undefined) query.set("limit", String(params.limit));
  if (params.offset !== undefined) query.set("offset", String(params.offset));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<Project[]>(`/projects${suffix}`, { token });
}

export function createProject(
  token: string,
  payload: { name: string; description?: string | null },
): Promise<Project> {
  return request<Project>("/projects", { method: "POST", body: payload, token });
}

export function archiveProject(token: string, projectId: string): Promise<void> {
  return request<void>(`/projects/${projectId}`, { method: "DELETE", token });
}

export function createJob(
  token: string,
  projectId: string,
  payload: { prompt: string; num_scenes: number; aspect: string; style: string },
): Promise<Job> {
  return request<Job>(`/projects/${projectId}/jobs`, {
    method: "POST",
    body: payload,
    token,
  });
}

export function listJobs(token: string, projectId: string): Promise<Job[]> {
  return request<Job[]>(`/projects/${projectId}/jobs`, { token });
}

export function fetchJob(token: string, jobId: string): Promise<Job> {
  return request<Job>(`/jobs/${jobId}`, { token });
}

export function cancelJob(token: string, jobId: string): Promise<Job> {
  return request<Job>(`/jobs/${jobId}/cancel`, { method: "POST", token });
}

export function fetchStreamTicket(token: string, jobId: string): Promise<StreamTicket> {
  return request<StreamTicket>(`/jobs/${jobId}/stream-ticket`, { method: "POST", token });
}

/**
 * Native EventSource cannot send the Bearer header, so the caller first gets a
 * short-lived signed ticket and passes it in the query string instead.
 */
export function subscribeJobEvents(
  jobId: string,
  ticket: string,
  onEvent: (event: JobProgressEvent) => void,
  onError?: (error: Error) => void,
): () => void {
  const query = encodeURIComponent(ticket);
  const source = new EventSource(`${API}/jobs/${jobId}/events?ticket=${query}`);
  source.addEventListener("progress", (message) => {
    try {
      const payload = JSON.parse((message as MessageEvent<string>).data) as JobProgressEvent;
      onEvent(payload);
    } catch {
      onError?.(new Error("بيانات البث غير صالحة"));
    }
  });
  source.addEventListener("done", () => source.close());
  source.onerror = () => {
    source.close();
    onError?.(new Error("انقطع بث التقدم - سيستمر التحديث الدوري"));
  };
  return () => source.close();
}

export function refreshSession(): Promise<TokenResponse> {
  return request<TokenResponse>("/auth/refresh", {
    method: "POST",
    allowRefresh: false,
  });
}

export function logoutRequest(): Promise<{ status: string }> {
  return request<{ status: string }>("/auth/logout", {
    method: "POST",
    token: accessToken,
    allowRefresh: false,
  });
}
