import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { useApi } from "./useApi";
import { api, ApiError } from "../api/client";

vi.mock("../api/client", async (original) => ({ ...await original<typeof import("../api/client")>(), api: vi.fn() }));
afterEach(() => { cleanup(); vi.useRealTimers(); vi.resetAllMocks(); });

it("aborts old route requests and does not overwrite a newer page", async () => {
  let finishOld: (value: string) => void = () => {};
  vi.mocked(api).mockImplementationOnce(() => new Promise((resolve) => { finishOld = resolve; }));
  const { result, rerender } = renderHook(({ path }) => useApi<string>(path), { initialProps: { path: "/old" } });
  const oldSignal = vi.mocked(api).mock.calls[0][1]!.signal!;
  vi.mocked(api).mockResolvedValueOnce("new page");
  rerender({ path: "/new" });
  await waitFor(() => expect(result.current.data).toBe("new page"));
  await act(async () => { finishOld("old page"); });
  expect(oldSignal.aborted).toBe(true);
  expect(result.current.data).toBe("new page");
});

it("resumes polling after an outage and cancels it on unmount", async () => {
  vi.useFakeTimers();
  vi.mocked(api).mockRejectedValueOnce(new ApiError(0, "NETWORK", "offline")).mockResolvedValue("recovered");
  const { result, unmount } = renderHook(() => useApi<string>("/status", () => 1000));
  await act(async () => { await vi.advanceTimersByTimeAsync(10_000); });
  expect(result.current.data).toBe("recovered");
  unmount();
  const calls = vi.mocked(api).mock.calls.length;
  await vi.advanceTimersByTimeAsync(20_000);
  expect(api).toHaveBeenCalledTimes(calls);
});
