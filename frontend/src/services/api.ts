/** Typed HTTP client. All backend access goes through this module. */

export interface HealthResponse {
  status: string;
  service: string;
  environment: string;
  timestamp: string;
}

const API_BASE = "/api/v1";
const REQUEST_TIMEOUT_MS = 8000;

export class ApiError extends Error {
  readonly status?: number;

  constructor(message: string, status?: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { Accept: "application/json", ...init.headers },
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
  } catch (error) {
    const reason = error instanceof DOMException && error.name === "TimeoutError"
      ? "انتهت مهلة الاتصال بالخادم"
      : "تعذّر الوصول إلى الخادم";
    throw new ApiError(reason);
  }

  if (!response.ok) {
    throw new ApiError(`الخادم أعاد حالة ${response.status}`, response.status);
  }

  try {
    return (await response.json()) as T;
  } catch {
    throw new ApiError("استجابة الخادم ليست JSON صالحًا", response.status);
  }
}

/** Proves the browser → Vite proxy → FastAPI path end to end. */
export function checkHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/health");
}
