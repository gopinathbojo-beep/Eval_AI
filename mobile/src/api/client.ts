import { Platform } from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";
import Constants from "expo-constants";
import * as FileSystem from "expo-file-system/legacy";
import * as Sharing from "expo-sharing";
import type { Issue } from "../types";

const TOKEN_KEY = "adem_mobile_token";
const BASE_URL_KEY = "adem_backend_url";

/**
 * Automatically discovers the PC backend URL.
 * When running with Expo Go on a real phone, Constants.expoConfig?.hostUri
 * contains the computer's LAN IP address (e.g. 10.195.96.202:8081).
 */
export function getDefaultBackendUrl(): string {
  const hostUri =
    Constants.expoConfig?.hostUri ||
    (Constants as any).manifest2?.extra?.expoClient?.hostUri ||
    (Constants as any).manifest?.debuggerHost;

  if (hostUri) {
    const ip = hostUri.split(":")[0];
    if (ip && ip !== "localhost" && ip !== "127.0.0.1") {
      return `http://${ip}:8000`;
    }
  }

  // Fallback for Android emulator
  return Platform.OS === "android" ? "http://10.0.2.2:8000" : "http://127.0.0.1:8000";
}

export const DEFAULT_BACKEND_URL = getDefaultBackendUrl();

let cachedBaseUrl: string | null = null;

export async function getBaseUrl(): Promise<string> {
  if (cachedBaseUrl) return cachedBaseUrl;
  const stored = await AsyncStorage.getItem(BASE_URL_KEY);
  const detected = getDefaultBackendUrl();

  const isRealIp = (url: string) =>
    url && !url.includes("10.0.2.2") && !url.includes("127.0.0.1") && !url.includes("localhost");

  // If Metro detected an active LAN IP, but stored has a stale/different IP from a previous Wi-Fi network,
  // automatically update to the current active LAN IP
  if (isRealIp(detected) && (!stored || !isRealIp(stored) || stored !== detected)) {
    cachedBaseUrl = detected;
    await AsyncStorage.setItem(BASE_URL_KEY, detected);
  } else if (stored) {
    cachedBaseUrl = stored;
  } else {
    cachedBaseUrl = detected;
  }

  return cachedBaseUrl;
}

export async function setBaseUrl(url: string): Promise<void> {
  const clean = url.trim().replace(/\/+$/, "");
  cachedBaseUrl = clean;
  await AsyncStorage.setItem(BASE_URL_KEY, clean);
}

export async function resetToDefaultUrl(): Promise<string> {
  const detected = getDefaultBackendUrl();
  cachedBaseUrl = detected;
  await AsyncStorage.setItem(BASE_URL_KEY, detected);
  return detected;
}

export const getToken = async (): Promise<string | null> => {
  return AsyncStorage.getItem(TOKEN_KEY);
};

export const setToken = async (token: string | null): Promise<void> => {
  if (token) {
    await AsyncStorage.setItem(TOKEN_KEY, token);
  } else {
    await AsyncStorage.removeItem(TOKEN_KEY);
  }
};

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public issues: Issue[] = []
  ) {
    super(message);
  }
}

let onUnauthorizedHandler: (() => void) | null = null;
export const setUnauthorizedHandler = (fn: () => void) => {
  onUnauthorizedHandler = fn;
};

async function toError(res: Response): Promise<ApiError> {
  let body: { code?: string; message?: string; issues?: Issue[] } = {};
  try {
    body = await res.json();
  } catch {
    // not JSON
  }
  return new ApiError(
    res.status,
    body.code ?? "ERROR",
    body.message ?? `Request failed (HTTP ${res.status}).`,
    body.issues ?? []
  );
}

export async function api<T = unknown>(
  path: string,
  opts: { method?: string; json?: unknown; formData?: FormData; timeoutMs?: number } = {}
): Promise<T> {
  const baseUrl = await getBaseUrl();
  const token = await getToken();
  const headers: Record<string, string> = {};

  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  let body: BodyInit | undefined;
  if (opts.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.json);
  } else if (opts.formData) {
    body = opts.formData;
  }

  const fullUrl = `${baseUrl}/api${path.startsWith("/") ? path : `/${path}`}`;

  // Allow 3 minutes (180s) for AI generation/evaluation, 60s for file uploads, 30s for regular requests
  const isAiEndpoint =
    path.includes("generate-ai") ||
    path.includes("evaluat") ||
    path.includes("results") ||
    path.includes("save-ai");
  const defaultTimeout = isAiEndpoint ? 180000 : (opts.formData ? 60000 : 30000);
  const controller = new AbortController();
  const timeoutMs = opts.timeoutMs ?? defaultTimeout;
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  let res: Response;
  try {
    res = await fetch(fullUrl, {
      method: opts.method ?? "GET",
      headers,
      body,
      signal: controller.signal,
    });
  } catch (err: any) {
    if (err.name === "AbortError") {
      throw new ApiError(
        0,
        "TIMEOUT",
        isAiEndpoint
          ? "The AI model is taking longer than usual to complete. Please try again."
          : `Connection timed out connecting to ${baseUrl}. Check that your phone is on the same Wi-Fi and that the PC firewall allows port 8000.`
      );
    }
    throw new ApiError(
      0,
      "NETWORK",
      `Cannot connect to Eval AI backend at ${baseUrl}. Ensure the backend is running on 0.0.0.0:8000 and the URL is reachable from your phone.`
    );
  } finally {
    clearTimeout(timeoutId);
  }

  if (res.status === 401 && !path.includes("/auth/login")) {
    await setToken(null);
    onUnauthorizedHandler?.();
  }

  if (!res.ok) {
    throw await toError(res);
  }

  return (await res.json()) as T;
}

/**
 * Downloads a file from the backend and opens the native mobile share sheet.
 */
export async function downloadAndShareFile(
  path: string,
  fallbackFilename = "EvalAI_Report.pdf"
): Promise<void> {
  const baseUrl = await getBaseUrl();
  const token = await getToken();
  const fullUrl = `${baseUrl}/api${path.startsWith("/") ? path : `/${path}`}`;

  const cleanFilename = fallbackFilename.replace(/[^a-zA-Z0-9._-]/g, "_");
  const fileUri = `${FileSystem.cacheDirectory}${cleanFilename}`;

  // Remove existing file if present to guarantee a fresh download
  const info = await FileSystem.getInfoAsync(fileUri);
  if (info.exists) {
    await FileSystem.deleteAsync(fileUri, { idempotent: true });
  }

  const downloadResult = await FileSystem.downloadAsync(fullUrl, fileUri, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });

  if (downloadResult.status !== 200) {
    let errorDetail = "";
    try {
      const errText = await FileSystem.readAsStringAsync(downloadResult.uri);
      const parsed = JSON.parse(errText);
      errorDetail = parsed.detail || parsed.message || "";
    } catch {
      // not json or unreadable
    }
    throw new Error(
      `Failed to download report (HTTP ${downloadResult.status})${errorDetail ? `: ${errorDetail}` : "."}`
    );
  }

  const isXlsx = cleanFilename.endsWith(".xlsx");
  const mimeType = isXlsx
    ? "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    : "application/pdf";

  if (await Sharing.isAvailableAsync()) {
    await Sharing.shareAsync(downloadResult.uri, {
      mimeType,
      dialogTitle: isXlsx ? "Share or Open Student Marksheet" : "Share or View PDF Report",
    });
  } else {
    throw new Error("Sharing is not available on this device.");
  }
}

/** POSTs JSON, saves the PDF that comes back (e.g. a template preview) and opens the share sheet. */
export async function postAndShareFile(path: string, json: unknown, filename = "preview.pdf"): Promise<void> {
  const baseUrl = await getBaseUrl();
  const token = await getToken();
  const res = await fetch(`${baseUrl}/api${path.startsWith("/") ? path : `/${path}`}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: JSON.stringify(json),
  });
  if (!res.ok) throw await toError(res);
  const fileUri = `${FileSystem.cacheDirectory}${filename.replace(/[^a-zA-Z0-9._-]/g, "_")}`;
  await FileSystem.writeAsStringAsync(fileUri, uint8ArrayToBase64(new Uint8Array(await res.arrayBuffer())), {
    encoding: FileSystem.EncodingType.Base64,
  });
  if (!(await Sharing.isAvailableAsync())) throw new Error("Sharing is not available on this device.");
  await Sharing.shareAsync(fileUri, { mimeType: "application/pdf", dialogTitle: "Preview" });
}

function base64ToUint8Array(base64: string): Uint8Array {
  const clean = base64.replace(/[\r\n\s]/g, "");
  if (typeof atob === "function") {
    const binStr = atob(clean);
    const len = binStr.length;
    const bytes = new Uint8Array(len);
    for (let i = 0; i < len; i++) {
      bytes[i] = binStr.charCodeAt(i);
    }
    return bytes;
  }
  const b64Chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  const lookup = new Uint8Array(256);
  for (let i = 0; i < b64Chars.length; i++) {
    lookup[b64Chars.charCodeAt(i)] = i;
  }
  let padding = 0;
  if (clean.endsWith("==")) padding = 2;
  else if (clean.endsWith("=")) padding = 1;
  const byteLength = (clean.length * 3) / 4 - padding;
  const bytes = new Uint8Array(byteLength);
  let p = 0;
  for (let i = 0; i < clean.length; i += 4) {
    const enc1 = lookup[clean.charCodeAt(i)];
    const enc2 = lookup[clean.charCodeAt(i + 1)];
    const enc3 = lookup[clean.charCodeAt(i + 2)];
    const enc4 = lookup[clean.charCodeAt(i + 3)];
    bytes[p++] = (enc1 << 2) | (enc2 >> 4);
    if (p < byteLength) bytes[p++] = ((enc2 & 15) << 4) | (enc3 >> 2);
    if (p < byteLength) bytes[p++] = ((enc3 & 3) << 6) | enc4;
  }
  return bytes;
}

function uint8ArrayToBase64(bytes: Uint8Array): string {
  if (typeof btoa === "function") {
    let binary = "";
    const len = bytes.byteLength;
    const chunkSize = 8192;
    for (let i = 0; i < len; i += chunkSize) {
      const chunk = bytes.subarray(i, Math.min(i + chunkSize, len));
      binary += String.fromCharCode.apply(null, chunk as any);
    }
    return btoa(binary);
  }
  const b64Chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  let result = "";
  const len = bytes.length;
  for (let i = 0; i < len; i += 3) {
    const b1 = bytes[i];
    const b2 = i + 1 < len ? bytes[i + 1] : 0;
    const b3 = i + 2 < len ? bytes[i + 2] : 0;
    result += b64Chars[b1 >> 2];
    result += b64Chars[((b1 & 3) << 4) | (b2 >> 4)];
    result += i + 1 < len ? b64Chars[((b2 & 15) << 2) | (b3 >> 6)] : "=";
    result += i + 2 < len ? b64Chars[b3 & 63] : "=";
  }
  return result;
}

function inferMimeAndExt(fileName?: string, uri?: string, mimeType?: string): { mime: string; ext: string } {
  let ext = "pdf";
  const candidate = (fileName || uri || "").toLowerCase();
  if (candidate.endsWith(".pdf")) ext = "pdf";
  else if (candidate.endsWith(".jpg") || candidate.endsWith(".jpeg")) ext = "jpg";
  else if (candidate.endsWith(".png")) ext = "png";
  else if (candidate.endsWith(".docx")) ext = "docx";
  else if (candidate.includes(".")) {
    const parts = candidate.split(".");
    ext = parts[parts.length - 1].replace(/[^a-z0-9]/g, "") || "pdf";
  }

  let mime = mimeType;
  if (!mime || mime === "application/octet-stream" || mime === "*/*") {
    if (ext === "pdf") mime = "application/pdf";
    else if (ext === "jpg" || ext === "jpeg") mime = "image/jpeg";
    else if (ext === "png") mime = "image/png";
    else if (ext === "docx") mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
    else mime = "application/pdf";
  }
  return { mime, ext };
}

function readLocalUriAsBlob(uri: string): Promise<Blob> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.onload = () => {
      if (xhr.response) {
        resolve(xhr.response as Blob);
      } else {
        reject(new Error("Empty response from local file XHR"));
      }
    };
    xhr.onerror = () => reject(new Error("XHR failed to read local URI"));
    xhr.ontimeout = () => reject(new Error("XHR timed out reading local URI"));
    xhr.responseType = "blob";
    xhr.open("GET", uri, true);
    xhr.send(null);
  });
}

function readLocalUriAsArrayBuffer(uri: string): Promise<ArrayBuffer> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.onload = () => {
      if (xhr.response) {
        resolve(xhr.response as ArrayBuffer);
      } else {
        reject(new Error("Empty response from local file XHR"));
      }
    };
    xhr.onerror = () => reject(new Error("XHR failed to read local URI"));
    xhr.ontimeout = () => reject(new Error("XHR timed out reading local URI"));
    xhr.responseType = "arraybuffer";
    xhr.open("GET", uri, true);
    xhr.send(null);
  });
}

/**
 * Uploads a document reliably across Android, iOS and Web.
 * Copies scoped content:// and temporary picker URIs into an app-owned cache
 * directory to guarantee native file readability by ExponentFileSystem.uploadAsync.
 * Includes a robust multipart FormData fallback that uses native Blobs without
 * triggering React Native / Expo's "Unsupported FormDataPart implementation" error.
 */
export async function uploadFileNative<T = unknown>(
  path: string,
  fileUri: string,
  opts: {
    fieldName?: string;
    fileName?: string;
    mimeType?: string;
    params?: Record<string, string>;
  } = {}
): Promise<T> {
  if (!fileUri || typeof fileUri !== "string") {
    throw new ApiError(400, "INVALID_FILE_URI", "No valid file was selected for upload.");
  }

  const baseUrl = await getBaseUrl();
  const token = await getToken();
  const fullUrl = `${baseUrl}/api${path.startsWith("/") ? path : `/${path}`}`;

  const headers: Record<string, string> = {};
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const { mime: resolvedMime, ext } = inferMimeAndExt(opts.fileName, fileUri, opts.mimeType);
  const rawName = opts.fileName
    ? opts.fileName.replace(/[^a-zA-Z0-9._-]/g, "_")
    : (fileUri.split("/").pop() || "upload_document").replace(/[^a-zA-Z0-9._-]/g, "_");
  const resolvedFileName = rawName.includes(".") ? rawName : `${rawName}.${ext}`;

  // Ensure file URI format is well-formed
  let cleanSourceUri = fileUri;
  if (!cleanSourceUri.startsWith("file://") && !cleanSourceUri.startsWith("content://")) {
    cleanSourceUri = `file://${cleanSourceUri}`;
  }

  // Stage file into an app-owned cache directory.
  // FileSystem.copyAsync correctly streams content:// streams from Android's ContentResolver
  // into a readable file:// cache path.
  const stagingDir = `${FileSystem.cacheDirectory}adem_uploads/`;
  try {
    const dirInfo = await FileSystem.getInfoAsync(stagingDir);
    if (!dirInfo.exists) {
      await FileSystem.makeDirectoryAsync(stagingDir, { intermediates: true });
    }
  } catch {
    // Proceed if directory already exists
  }

  const stagedUri = `${stagingDir}${Date.now()}_${resolvedFileName}`;
  let targetLocalUri = cleanSourceUri;

  // Attempt direct FileSystem.copyAsync first
  let copySucceeded = false;
  try {
    await FileSystem.copyAsync({ from: cleanSourceUri, to: stagedUri });
    targetLocalUri = stagedUri;
    copySucceeded = true;
  } catch {
    // Handled below without console.warn to avoid Expo LogBox banners
  }

  // If FileSystem.copyAsync failed (e.g. DocumentPicker file:// URI outside Expo Go sandbox),
  // read the file bytes via XHR (which bypasses Expo Go's scoped storage restrictions)
  // and write them to our cache directory.
  if (!copySucceeded) {
    try {
      const buffer = await readLocalUriAsArrayBuffer(cleanSourceUri);
      if (buffer && buffer.byteLength > 0) {
        const base64Data = uint8ArrayToBase64(new Uint8Array(buffer));
        await FileSystem.writeAsStringAsync(stagedUri, base64Data, {
          encoding: FileSystem.EncodingType.Base64,
        });
        targetLocalUri = stagedUri;
        copySucceeded = true;
      }
    } catch {
      // Secondary fallback via fetch
      try {
        const fileResponse = await fetch(cleanSourceUri);
        const buffer = await fileResponse.arrayBuffer();
        if (buffer && buffer.byteLength > 0) {
          const base64Data = uint8ArrayToBase64(new Uint8Array(buffer));
          await FileSystem.writeAsStringAsync(stagedUri, base64Data, {
            encoding: FileSystem.EncodingType.Base64,
          });
          targetLocalUri = stagedUri;
          copySucceeded = true;
        }
      } catch {
        // Proceed with targetLocalUri
      }
    }
  }

  // Validate staged file existence, non-emptiness, and max upload size (50MB)
  try {
    const check = await FileSystem.getInfoAsync(targetLocalUri);
    if (check.exists && check.size) {
      const maxBytes = 50 * 1024 * 1024;
      if (check.size > maxBytes) {
        throw new ApiError(
          413,
          "FILE_TOO_LARGE",
          `File size (${(check.size / (1024 * 1024)).toFixed(1)} MB) exceeds the maximum allowed limit of 50 MB.`
        );
      }
    }
  } catch (statErr: any) {
    if (statErr instanceof ApiError) throw statErr;
  }

  // Primary Path: Native multipart streaming upload via expo-file-system
  let nativeUploadError: any = null;
  try {
    const res = await FileSystem.uploadAsync(fullUrl, targetLocalUri, {
      httpMethod: "POST",
      uploadType: FileSystem.FileSystemUploadType.MULTIPART,
      fieldName: opts.fieldName || "file",
      mimeType: resolvedMime,
      headers,
      parameters: opts.params,
    });

    if (res.status >= 400) {
      let errorMsg = `Upload failed (HTTP ${res.status})`;
      try {
        const parsed = JSON.parse(res.body);
        if (parsed.detail?.message) errorMsg = parsed.detail.message;
        else if (parsed.message) errorMsg = parsed.message;
        else if (typeof parsed.detail === "string") errorMsg = parsed.detail;
      } catch {}
      throw new ApiError(res.status, "UPLOAD_ERROR", errorMsg);
    }

    try {
      return JSON.parse(res.body) as T;
    } catch {
      return {} as T;
    }
  } catch (uploadErr: any) {
    if (uploadErr instanceof ApiError) {
      throw uploadErr;
    }
    nativeUploadError = uploadErr;
  }

  // Fallback: Standard fetch using multipart FormData with a real binary Blob
  // (Prevents "Unsupported FormDataPart implementation" in modern Expo/React Native fetch)
  try {
    let blob: Blob;
    try {
      if (targetLocalUri.startsWith(FileSystem.cacheDirectory || "")) {
        const base64 = await FileSystem.readAsStringAsync(targetLocalUri, {
          encoding: FileSystem.EncodingType.Base64,
        });
        const bytes = base64ToUint8Array(base64);
        blob = new Blob([bytes as any], { type: resolvedMime });
      } else {
        throw new Error("Target URI is outside app cache directory");
      }
    } catch {
      // If FileSystem.readAsStringAsync fails, read blob via XHR or fetch
      try {
        blob = await readLocalUriAsBlob(cleanSourceUri);
      } catch {
        const fileRes = await fetch(cleanSourceUri);
        const buf = await fileRes.arrayBuffer();
        blob = new Blob([new Uint8Array(buf) as any], { type: resolvedMime });
      }
    }

    const formData = new FormData();
    formData.append(opts.fieldName || "file", blob, resolvedFileName);

    if (opts.params) {
      for (const [k, v] of Object.entries(opts.params)) {
        formData.append(k, v);
      }
    }

    const fetchHeaders: Record<string, string> = {};
    if (token) {
      fetchHeaders.Authorization = `Bearer ${token}`;
    }
    // Do NOT set Content-Type header; runtime generates multipart boundary automatically

    const response = await fetch(fullUrl, {
      method: "POST",
      headers: fetchHeaders,
      body: formData,
    });

    if (!response.ok) {
      const text = await response.text();
      let errorMsg = `Upload failed (HTTP ${response.status})`;
      try {
        const parsed = JSON.parse(text);
        if (parsed.detail?.message) errorMsg = parsed.detail.message;
        else if (parsed.message) errorMsg = parsed.message;
        else if (typeof parsed.detail === "string") errorMsg = parsed.detail;
      } catch {}
      throw new ApiError(response.status, "UPLOAD_ERROR", errorMsg);
    }

    return (await response.json()) as T;
  } catch (fallbackErr: any) {
    if (fallbackErr instanceof ApiError) {
      throw fallbackErr;
    }

    if (
      fallbackErr?.message?.includes("Network request failed") ||
      nativeUploadError?.message?.includes("Network request failed") ||
      fallbackErr?.message?.includes("Failed to connect")
    ) {
      throw new ApiError(
        0,
        "NETWORK_ERROR",
        "Cannot connect to the backend server. Please verify your network connection and server settings."
      );
    }

    const rawError = fallbackErr?.message || nativeUploadError?.message || "";
    let friendlyError = rawError;
    if (rawError.includes("isn't readable") || rawError.includes("readAsStringAsync")) {
      friendlyError = "The selected file could not be read. Please try selecting the file again or use the camera scanner.";
    }

    throw new ApiError(
      500,
      "UPLOAD_FAILED",
      friendlyError || "Failed to upload document."
    );
  }
}


