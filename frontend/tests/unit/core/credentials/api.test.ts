import { afterEach, expect, test, vi } from "vitest";

import {
  clearCredential,
  listCredentials,
  updateCredential,
} from "@/core/credentials/api";

afterEach(() => {
  vi.restoreAllMocks();
});

test("listCredentials returns the parsed credentials array", async () => {
  const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(
      JSON.stringify({
        credentials: [
          {
            skill_name: "kalshi",
            fields: [
              { name: "api_key_id", label: "API Key ID", type: "text" },
              {
                name: "api_private_key",
                label: "Private Key",
                type: "textarea",
              },
            ],
            configured: false,
            fields_set: [],
            has_token: false,
            token_expires_at: null,
            updated_at: null,
          },
        ],
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    ),
  );

  const credentials = await listCredentials();

  expect(fetchSpy).toHaveBeenCalledTimes(1);
  expect(fetchSpy.mock.calls[0]?.[0]).toMatch(/\/api\/credentials$/);
  expect(credentials).toHaveLength(1);
  expect(credentials[0]?.skill_name).toBe("kalshi");
  expect(credentials[0]?.fields).toHaveLength(2);
});

test("updateCredential PUTs only the supplied field values", async () => {
  const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(
      JSON.stringify({
        skill_name: "kalshi",
        fields: [],
        configured: true,
        fields_set: ["api_key_id"],
        has_token: false,
        token_expires_at: null,
        updated_at: "2026-05-09T00:00:00Z",
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    ),
  );

  await updateCredential("kalshi", { api_key_id: "abc-123" });

  expect(fetchSpy).toHaveBeenCalledTimes(1);
  const [url, init] = fetchSpy.mock.calls[0]!;
  expect(url).toMatch(/\/api\/credentials\/kalshi$/);
  expect(init?.method).toBe("PUT");
  expect(JSON.parse(init?.body as string)).toEqual({
    field_values: { api_key_id: "abc-123" },
  });
});

test("updateCredential url-encodes skill names", async () => {
  const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response("{}", {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );

  await updateCredential("foo bar/baz", { x: "1" });

  const url = fetchSpy.mock.calls[0]?.[0];
  expect(typeof url).toBe("string");
  expect(url as string).toContain("foo%20bar%2Fbaz");
});

test("clearCredential issues DELETE", async () => {
  const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ success: true }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );

  await clearCredential("kalshi");

  expect(fetchSpy).toHaveBeenCalledTimes(1);
  const [url, init] = fetchSpy.mock.calls[0]!;
  expect(url).toMatch(/\/api\/credentials\/kalshi$/);
  expect(init?.method).toBe("DELETE");
});

test("listCredentials surfaces backend error detail", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ detail: "explosion" }), {
      status: 500,
      headers: { "Content-Type": "application/json" },
    }),
  );

  await expect(listCredentials()).rejects.toThrow("explosion");
});
