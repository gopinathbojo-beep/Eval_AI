import type { Issue } from "../types";

const TOKEN_KEY = "adem_token";
export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const setToken = (t: string | null) => (t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY));

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public issues: Issue[] = []) {
    super(message);
  }
}

let onUnauthorized: () => void = () => {};
export const setUnauthorizedHandler = (fn: () => void) => (onUnauthorized = fn);

async function toError(res: Response): Promise<ApiError> {
  let body: { code?: string; message?: string; issues?: Issue[] } = {};
  try { body = await res.json(); } catch { /* not JSON */ }
  return new ApiError(res.status, body.code ?? "ERROR", body.message ?? `Request failed (HTTP ${res.status}).`, body.issues ?? []);
}

export async function api<T = unknown>(path: string, opts: { method?: string; json?: unknown; form?: FormData } = {}): Promise<T> {
  const headers: Record<string, string> = {};
  const t = getToken();
  if (t) headers.Authorization = `Bearer ${t}`;
  let body: BodyInit | undefined;
  if (opts.json !== undefined) { headers["Content-Type"] = "application/json"; body = JSON.stringify(opts.json); }
  if (opts.form) body = opts.form;
  let res: Response;
  try {
    res = await fetch(`/api${path}`, { method: opts.method ?? "GET", headers, body });
  } catch {
    throw new ApiError(0, "NETWORK", "Cannot reach the ADEM server. Start the backend (uvicorn app.main:app) and try again.");
  }
  if (res.status === 401 && path !== "/auth/login") { setToken(null); onUnauthorized(); }
  if (!res.ok) throw await toError(res);
  return (await res.json()) as T;
}

export async function fetchBlobUrl(path: string): Promise<string> {
  const t = getToken();
  const res = await fetch(`/api${path}`, { headers: t ? { Authorization: `Bearer ${t}` } : {} });
  if (!res.ok) throw await toError(res);
  return URL.createObjectURL(await res.blob());
}

export async function downloadFile(path: string, fallbackFilename = "download.pdf"): Promise<void> {
  const t = getToken();
  let res: Response;
  try {
    res = await fetch(`/api${path}`, { headers: t ? { Authorization: `Bearer ${t}` } : {} });
  } catch {
    throw new ApiError(0, "NETWORK", "Cannot reach the ADEM server. Start the backend (uvicorn app.main:app) and try again.");
  }
  if (res.status === 401) { setToken(null); onUnauthorized(); }
  if (!res.ok) throw await toError(res);
  const blob = await res.blob();
  const disposition = res.headers.get("Content-Disposition");
  let filename = fallbackFilename;
  if (disposition) {
    const utf8Match = disposition.match(/filename\*=UTF-8''([^;\r\n]+)/i);
    const standardMatch = disposition.match(/filename=["']?([^";\r\n]+)["']?/i);
    if (utf8Match && utf8Match[1]) {
      try { filename = decodeURIComponent(utf8Match[1]); } catch { /* ignore decode error */ }
    } else if (standardMatch && standardMatch[1]) {
      filename = standardMatch[1].trim();
    }
  }
  const blobUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = blobUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(blobUrl), 1000);
}
