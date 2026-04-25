import { afterEach, expect, test, vi } from "vitest";

import { enableLibrarySkill, loadLibrarySkills } from "@/core/library-skills/api";

afterEach(() => {
  vi.restoreAllMocks();
});

test("loadLibrarySkills returns the parsed skills array", async () => {
  const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(
      JSON.stringify({
        skills: [
          {
            name: "alpha",
            description: "first",
            license: "MIT",
            enabled: true,
            path: "/mnt/skill-library/alpha/SKILL.md",
          },
        ],
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    ),
  );

  const skills = await loadLibrarySkills();

  expect(fetchSpy).toHaveBeenCalledTimes(1);
  expect(fetchSpy.mock.calls[0]?.[0]).toMatch(/\/api\/library-skills$/);
  expect(skills).toEqual([
    {
      name: "alpha",
      description: "first",
      license: "MIT",
      enabled: true,
      path: "/mnt/skill-library/alpha/SKILL.md",
    },
  ]);
});

test("enableLibrarySkill issues a PUT to the skill endpoint with the enabled flag", async () => {
  const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(
      JSON.stringify({
        name: "alpha",
        description: "first",
        license: "MIT",
        enabled: false,
        path: "/mnt/skill-library/alpha/SKILL.md",
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    ),
  );

  await enableLibrarySkill("alpha", false);

  expect(fetchSpy).toHaveBeenCalledTimes(1);
  const [url, init] = fetchSpy.mock.calls[0]!;
  expect(url).toMatch(/\/api\/library-skills\/alpha$/);
  expect(init?.method).toBe("PUT");
  expect(init?.headers).toMatchObject({ "Content-Type": "application/json" });
  expect(JSON.parse(String(init?.body))).toEqual({ enabled: false });
});
