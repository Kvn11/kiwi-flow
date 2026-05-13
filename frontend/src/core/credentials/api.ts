import { getBackendBaseURL } from "@/core/config";

import type {
  CredentialEntry,
  CredentialListResponse,
  CredentialUpdateRequest,
} from "./types";

async function parseJsonOrThrow(response: Response): Promise<unknown> {
  if (!response.ok) {
    const errorBody = await response.json().catch(() => ({}));
    const detail =
      (errorBody as { detail?: string }).detail ??
      `HTTP ${response.status}: ${response.statusText}`;
    throw new Error(detail);
  }
  return response.json();
}

export async function listCredentials(): Promise<CredentialEntry[]> {
  const response = await fetch(`${getBackendBaseURL()}/api/credentials`);
  const json = (await parseJsonOrThrow(response)) as CredentialListResponse;
  return json.credentials;
}

export async function updateCredential(
  skillName: string,
  fieldValues: Record<string, string>,
): Promise<CredentialEntry> {
  const body: CredentialUpdateRequest = { field_values: fieldValues };
  const response = await fetch(
    `${getBackendBaseURL()}/api/credentials/${encodeURIComponent(skillName)}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
  return (await parseJsonOrThrow(response)) as CredentialEntry;
}

export async function clearCredential(skillName: string): Promise<void> {
  const response = await fetch(
    `${getBackendBaseURL()}/api/credentials/${encodeURIComponent(skillName)}`,
    { method: "DELETE" },
  );
  await parseJsonOrThrow(response);
}
