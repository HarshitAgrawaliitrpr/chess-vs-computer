import { describe, expect, it, vi, afterEach } from "vitest";
import { EngineError, fetchComputerMove } from "../api/engineClient.js";

describe("fetchComputerMove", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("POSTs the FEN and difficulty to /api/engine/move", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ move: { from: "e2", to: "e4" } }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await fetchComputerMove({ fen: "startpos-fen", difficulty: "hard" });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/engine/move");
    expect(options.method).toBe("POST");
    expect(JSON.parse(options.body)).toEqual({ fen: "startpos-fen", difficulty: "hard" });
  });

  it("omits optional overrides when not provided", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
    vi.stubGlobal("fetch", fetchMock);

    await fetchComputerMove({ fen: "f" });
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ fen: "f", difficulty: "medium" });
  });

  it("surfaces backend error detail as an EngineError", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 422,
      json: async () => ({ detail: "Invalid FEN: boom" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(fetchComputerMove({ fen: "bad" })).rejects.toThrow(EngineError);
    await expect(fetchComputerMove({ fen: "bad" })).rejects.toThrow("Invalid FEN: boom");
  });
});