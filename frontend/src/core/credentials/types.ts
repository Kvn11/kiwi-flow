export type CredentialFieldType = "text" | "textarea";

export interface CredentialFieldSchema {
  name: string;
  label: string;
  type: CredentialFieldType;
}

export interface CredentialEntry {
  skill_name: string;
  fields: CredentialFieldSchema[];
  configured: boolean;
  fields_set: string[];
  has_token: boolean;
  token_expires_at: number | null;
  updated_at: string | null;
}

export interface CredentialListResponse {
  credentials: CredentialEntry[];
}

export interface CredentialUpdateRequest {
  field_values: Record<string, string>;
}
