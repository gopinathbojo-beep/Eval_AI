import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, fetchBlobUrl, postBlobUrl, setUnauthorizedHandler } from "./client";

describe("API session handling", () => {
  beforeEach(() => { vi.stubGlobal("fetch", vi.fn()); });
  afterEach(() => { vi.unstubAllGlobals(); setUnauthorizedHandler(() => {}); });

  it("uses same-origin cookies and a CSRF header without a bearer token", async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ ok: true })));
    expect(await api("/auth/login", { method: "POST", json: { browser_session: true } })).toEqual({ ok: true });
    const options = vi.mocked(fetch).mock.calls[0][1]!;
    expect(options.credentials).toBe("same-origin");
    expect(options.headers).toMatchObject({ "X-Requested-With": "EvalAI", "Content-Type": "application/json" });
    expect(options.headers).not.toHaveProperty("Authorization");
  });

  it("accepts empty logout responses", async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(null, { status: 204 }));
    expect(await api("/auth/logout", { method: "POST" })).toBeUndefined();
  });

  it.each(["json", "image", "preview"])("expires the session on %s requests", async (kind) => {
    const unauthorized = vi.fn();
    setUnauthorizedHandler(unauthorized);
    vi.mocked(fetch).mockResolvedValue(new Response("{}", { status: 401 }));
    const request = kind === "json" ? api("/auth/me") : kind === "image" ? fetchBlobUrl("/image") : postBlobUrl("/preview", {});
    await expect(request).rejects.toMatchObject({ status: 401 });
    expect(unauthorized).toHaveBeenCalledOnce();
  });

  it("reports proxy/network failures without developer startup instructions", async () => {
    vi.mocked(fetch).mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(api("/dashboard")).rejects.toMatchObject({ code: "NETWORK" });
  });
});
