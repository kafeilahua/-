import { describe, it, expect, vi, afterEach } from "vitest";
import { api, send, setCsrf } from "./api";
describe("authenticated API boundary", () => {
  afterEach(() => vi.unstubAllGlobals());
  it("sends the session cookie and CSRF token on answer changes", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ ok: true })));
    vi.stubGlobal("fetch", fetch);
    setCsrf("csrf-value");
    await send("/sessions/one/answer", { answer: ["A"] }, "PUT");
    expect(fetch).toHaveBeenCalledWith(
      "/api/v1/sessions/one/answer",
      expect.objectContaining({
        method: "PUT",
        credentials: "same-origin",
        headers: expect.objectContaining({ "X-CSRF-Token": "csrf-value" }),
      }),
    );
  });
  it("surfaces version conflicts without treating them as saved", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response(JSON.stringify({ detail: "记录已在其他页面更新" }), {
            status: 409,
          }),
        ),
    );
    await expect(send("/sessions/one/answer", {})).rejects.toThrow(
      "记录已在其他页面更新",
    );
  });
  it("provides readable validation errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response(
            JSON.stringify({ detail: [{ loc: ["body", "count"] }] }),
            { status: 422 },
          ),
        ),
    );
    await expect(api("/sessions")).rejects.toThrow("输入内容不符合要求");
  });
});
