import type { Issue } from "../types";
import { API_BASE } from "../config/config";

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public issues: Issue[] = []) {
    super(message);
  }
}

let onUnauthorized: () => void = () => {};
export const setUnauthorizedHandler = (fn: () => void) => (onUnauthorized = fn);

let uploadPolicy: Promise<boolean> | null = null;

async function cloudUpload(path: string, form: FormData, signal?: AbortSignal): Promise<unknown> {
  const match = path.match(/^\/exams\/([^/]+)\/(question-paper|answer-key|answer-sheets)(\/bulk)?$/);
  if (!match) return undefined;
  const direct = await (uploadPolicy ??= request("/auth/providers").then(r => r.json()).then(p => !!p.direct_uploads).catch(() => { uploadPolicy = null; return false; }));
  if (!direct) return undefined;
  const files = [...form.getAll("file"), ...form.getAll("files")].filter((v): v is File => v instanceof File);
  if (!files.length) throw new Error("Choose a file to upload.");
  const kind = match[2] === "answer-sheets" ? "answer-sheet" : match[2];
  const results: any[] = [];
  for (const file of files) {
    const lease = await api<{id:string;upload_url:string;content_type:string}>(`/exams/${match[1]}/uploads`, {method:"POST",signal,json:{
      kind,filename:file.name,file_size:file.size,student_id:form.get("student_id")||null,
      student_name:form.get("student_name")||null,roll_number:form.get("roll_number")||null}});
    // The URL is a short-lived capability for one private object. No service key reaches the browser.
    const response = await fetch(lease.upload_url,{method:"PUT",body:file,signal,
      headers:{"Content-Type":lease.content_type}});
    if(!response.ok) throw new Error("The file could not be uploaded to private storage. Please try again.");
    results.push(await api(`/uploads/${lease.id}/complete`,{method:"POST",signal}));
  }
  return match[3] ? {uploaded:results.length,documents:results.map(r=>r.document??r)} : results[0];
}

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
  if (opts.form) {
    const uploaded = await cloudUpload(path, opts.form, opts.signal);
    if (uploaded !== undefined) return uploaded as T;
  }
  const headers: Record<string, string> = {};
  let body: BodyInit | undefined;
  if (opts.json !== undefined) { headers["Content-Type"] = "application/json"; body = JSON.stringify(opts.json); }
  if (opts.form) body = opts.form;
<<<<<<< 7c662e7:frontend/web/src/api/client.ts
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, { method: opts.method ?? "GET", headers, body });
  } catch {
    throw new ApiError(0, "NETWORK", "Cannot reach the ADEM server. Start the backend (uvicorn app.main:app) and try again.");
  }
  if (res.status === 401 && !path.startsWith("/auth/login") && !path.startsWith("/auth/google")) { setToken(null); onUnauthorized(); }
  if (!res.ok) throw await toError(res);
  return (await res.json()) as T;
}

export async function fetchBlobUrl(path: string): Promise<string> {
  const t = getToken();
  const res = await fetch(`${API_BASE}${path}`, { headers: t ? { Authorization: `Bearer ${t}` } : {} });
  if (!res.ok) throw await toError(res);
  return URL.createObjectURL(await res.blob());
}

export async function downloadFile(path: string, fallbackFilename = "download.pdf"): Promise<void> {
  const t = getToken();
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, { headers: t ? { Authorization: `Bearer ${t}` } : {} });
  } catch {
    throw new ApiError(0, "NETWORK", "Cannot reach the ADEM server. Start the backend (uvicorn app.main:app) and try again.");
  }
  if (res.status === 401) { setToken(null); onUnauthorized(); }
  if (!res.ok) throw await toError(res);
  const blob = await res.blob();
=======
  const res = await request(path, { method: opts.method ?? "GET", headers, body, signal: opts.signal });
  return res.status === 204 ? undefined as T : await res.json() as T;
}

export async function fetchBlobUrl(path: string): Promise<string> {
  return URL.createObjectURL(await (await request(path)).blob());
}

export async function downloadFile(path: string, fallbackFilename = "download.pdf"): Promise<void> {
  const res = await request(path);
>>>>>>> kishore/Version2.0:frontend/src/api/client.ts
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
<<<<<<< 7c662e7:frontend/web/src/api/client.ts
  const t = getToken();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (t) headers.Authorization = `Bearer ${t}`;
  const res = await fetch(`${API_BASE}${path}`, { method: "POST", headers, body: JSON.stringify(json), signal });
  if (!res.ok) throw await toError(res);
=======
  const res = await request(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(json), signal });
>>>>>>> kishore/Version2.0:frontend/src/api/client.ts
  return URL.createObjectURL(await res.blob());
}
