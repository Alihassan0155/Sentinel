export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message); }
}
export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api${path}`, { ...options, cache: "no-store", headers: {
    "Content-Type": "application/json", "X-Sentinel-CSRF": "1", ...options.headers,
  }});
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = Array.isArray(data.detail) ? data.detail.map((item: { msg: string }) => item.msg).join(". ") : data.detail;
    throw new ApiError(message || "Something went wrong. Please try again.", response.status);
  }
  return data;
}
export type User = { id: number; name: string; email: string };
export type Watch = { id: number; name: string; url: string; category: string; active: boolean; check_interval_minutes: number; last_checked_at: string | null };
export type Action = { id: number; title: string; status: "pending" | "in_progress" | "completed"; deadline: string | null; supporting_quote: string | null; source_urls: string[]; resource_status: string | null };
export type Finding = { id: number; watch_source_id: number; summary: string; why_it_matters: string; importance: string; detected_at: string; recommendation: { recommendation: string; reasons: string[]; priority: string; relevance_score: number }; actions: Action[]; investigation: { status: string; result: unknown } | null };
