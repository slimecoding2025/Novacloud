let csrf = "";

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) { super(message); }
}

export function setCsrf(t: string) { csrf = t; }

export async function api<T = unknown>(method: string, path: string, body?: unknown, headers: Record<string, string> = {}): Promise<T> {
  const h: Record<string, string> = { ...headers };
  if (body !== undefined && !(body instanceof Blob)) h["Content-Type"] = "application/json";
  if (method !== "GET") h["X-CSRF-Token"] = csrf;
  const r = await fetch(path, {
    method, headers: h, credentials: "same-origin",
    body: body === undefined ? undefined : body instanceof Blob ? body : JSON.stringify(body),
  });
  if (r.status === 204) return undefined as T;
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new ApiError(r.status, data?.error?.code ?? "error", data?.error?.message ?? r.statusText);
  return data as T;
}

export const newKey = () => crypto.randomUUID();
