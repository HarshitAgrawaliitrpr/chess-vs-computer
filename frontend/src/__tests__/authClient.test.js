import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { authApi, clearToken, getToken, setToken } from "../api/authClient.js";

describe("auth token storage", () => {
  beforeEach(() => clearToken());

  it("stores, reads and clears the JWT", () => {
    expect(getToken()).toBeNull();
    setToken("abc123");
    expect(getToken()).toBe("abc123");
    clearToken();
    expect(getToken()).toBeNull();
  });
});

describe("authApi", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    clearToken();
  });

  const ok = (data) => ({ ok: true, status: 200, json: async () => data });

  it("POSTs the register payload as JSON", async () => {
    const fetchMock = vi.fn().mockResolvedValue(ok({ token: "t", user: {} }));
    vi.stubGlobal("fetch", fetchMock);

    await authApi.register({ email: "a@b.co", name: "A", password: "castlerook1" });

    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/auth/register");
    expect(options.method).toBe("POST");
    expect(JSON.parse(options.body)).toEqual({
      email: "a@b.co",
      name: "A",
      password: "castlerook1",
    });
  });

  it("attaches the stored token as a Bearer header", async () => {
    setToken("token-xyz");
    const fetchMock = vi.fn().mockResolvedValue(ok([]));
    vi.stubGlobal("fetch", fetchMock);

    await authApi.listGames();

    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/games");
    expect(options.headers.Authorization).toBe("Bearer token-xyz");
  });

  it("surfaces a string detail from the server as an AuthError", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({ detail: "Incorrect email or password." }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(authApi.login({ email: "a@b.co", password: "x" })).rejects.toThrow(
      "Incorrect email or password.",
    );
  });

  it("uses the first validation message when detail is an array", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 422,
      json: async () => ({ detail: [{ msg: "String should have at least 8 characters" }] }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(authApi.register({})).rejects.toThrow(
      "String should have at least 8 characters",
    );
  });

  it("wraps network failures with a friendly message", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("network down")));

    await expect(authApi.me()).rejects.toThrow("Could not reach the server");
  });
});
