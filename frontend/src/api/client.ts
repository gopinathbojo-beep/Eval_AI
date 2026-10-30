import type { Issue } from "../types";

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public issues: Issue[] = []) {
    super(message);
  }
}

let onUnauthorized: () => void = () => {};
export const setUnauthorizedHandler = (fn: () => void) => (onUnauthorized = fn);

async function toError(res: Response): Promise<ApiError> {
  let body: { code?: string; message?: string; issues?: Issue[] } = {};
  try { body = await res.json(); } catch { /* proxy error may not be JSON */ }
  return new ApiError(res.status, body.code ?? "ERROR", body.message ?? `Request failed (HTTP ${res.status}).`, body.issues ?? []);
}

/** Same-origin API. The session cookie is HttpOnly; JavaScript never reads a token. */
async function request(path: string, init: RequestInit = {}): Promise<Response> {
  if (!path.startsWith("/") || path.startsWith("//")) throw new Error("Invalid API path");
  const controller = new AbortController();
  const abort = () => controller.abort();
  init.signal?.addEventListener("abort", abort, { once: true });
  if (init.signal?.aborted) controller.abort();
  const timeout = window.setTimeout(abort, 300_000);
  try {
    const res = await fetch(`/api${path}`, {
      ...init,
      credentials: "same-origin",
      headers: { "X-Requested-With": "EvalAI", ...init.headers },
      signal: controller.signal,
    });
    if (res.status === 401 && path !== "/auth/login") onUnauthorized();
    if (!res.ok) throw await toError(res);
    return res;
  } catch (error) {
    if (error instanceof ApiError || init.signal?.aborted) throw error;
    throw new ApiError(0, controller.signal.aborted ? "TIMEOUT" : "NETWORK",
      controller.signal.aborted ? "The request took too long. Check its status before trying again." : "Cannot reach the server. Check your connection and try again.");
  } finally {
    window.clearTimeout(timeout);
    init.signal?.removeEventListener("abort", abort);
  }
}

export async function api<T = unknown>(path: string, opts: { method?: string; json?: unknown; form?: FormData; signal?: AbortSignal } = {}): Promise<T> {
  const headers: Record<string, string> = {};
  let body: BodyInit | undefined;
  if (opts.json !== undefined) { headers["Content-Type"] = "application/json"; body = JSON.stringify(opts.json); }
  if (opts.form) body = opts.form;
  const res = await request(path, { method: opts.method ?? "GET", headers, body, signal: opts.signal });
  return res.status === 204 ? undefined as T : await res.json() as T;
}

export async function fetchBlobUrl(path: string): Promise<string> {
  return URL.createObjectURL(await (await request(path)).blob());
}

export async function downloadFile(path: string, fallbackFilename = "download.pdf"): Promise<void> {
  const res = await request(path);
  const disposition = res.headers.get("Content-Disposition");
  let filename = fallbackFilename;
  if (disposition) {
    const utf8Match = disposition.match(/filename\*=UTF-8''([^;\r\n]+)/i);
    const standardMatch = disposition.match(/filename=["']?([^";\r\n]+)["']?/i);
    if (utf8Match?.[1]) {
      try { filename = decodeURIComponent(utf8Match[1]); } catch { /* use fallback */ }
    } else if (standardMatch?.[1]) filename = standardMatch[1].trim();
  }
  const blobUrl = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = blobUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(blobUrl), 1000);
}

export async function postBlobUrl(path: string, json: unknown, signal?: AbortSignal): Promise<string> {
  const res = await request(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(json), signal });
  return URL.createObjectURL(await res.blob());
}
