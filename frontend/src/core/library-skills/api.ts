import { getBackendBaseURL } from "@/core/config";

import type { LibrarySkill } from "./type";

export async function loadLibrarySkills(): Promise<LibrarySkill[]> {
  const response = await fetch(`${getBackendBaseURL()}/api/library-skills`);
  const json = await response.json();
  return json.skills as LibrarySkill[];
}

export async function enableLibrarySkill(skillName: string, enabled: boolean): Promise<LibrarySkill> {
  const response = await fetch(
    `${getBackendBaseURL()}/api/library-skills/${skillName}`,
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ enabled }),
    },
  );
  return (await response.json()) as LibrarySkill;
}
