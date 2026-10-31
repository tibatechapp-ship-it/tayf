// ============================================================
// Tayf Studio - unified HTTP client (zero mock data)
// ------------------------------------------------------------
// HONESTY RULE: every function here calls the REAL backend
// through the Vite dev proxy ('/api' -> http://127.0.0.1:8000).
// There is no fake data, no fake latency, no fake success.
// ============================================================

const API = "/api/v1";
const TOKEN_KEY = "tayf.token";
const TIMEOUT_MS = 15_000;

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null): void {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

async function request<T>(
  path: string,
  options: { method?: string; body?: unknown; token?: string | null; timeout?: number } = {},
): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), options.timeout ?? TIMEOUT_MS);
  let response: Response;
  try {
    response = await fetch(API + path, {
      method: options.method ?? "GET",
      signal: controller.signal,
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

  if (response.status === 401 && options.token) {
    setToken(null); // stale/invalid token -> force a fresh login
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
  output_url: string | null;
  thumbnail_url: string | null;
  video_size_bytes: number | null;
  duration_seconds: number | null;
  credits_charged: number;
  created_at: string;
  completed_at: string | null;
  scenes: Scene[];
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
