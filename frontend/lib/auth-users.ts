import { getSupabaseAdmin } from "./supabase-admin";

export type AuthUserRecord = {
  id: string;
  email: string;
  name: string | null;
  google_id: string | null;
  password_hash: string | null;
};

export async function getUserByEmail(email: string): Promise<AuthUserRecord | null> {
  const normalizedEmail = email.trim().toLowerCase();
  const supabaseAdmin = getSupabaseAdmin();

  const { data, error } = await supabaseAdmin
    .from("users")
    .select("id, email, name, google_id, password_hash")
    .eq("email", normalizedEmail)
    .maybeSingle<AuthUserRecord>();

  if (error) {
    throw new Error(`Failed to load user: ${error.message}`);
  }

  return data ?? null;
}

export async function upsertGoogleUser(input: {
  googleId: string;
  email: string;
  name?: string | null;
}): Promise<AuthUserRecord> {
  const normalizedEmail = input.email.trim().toLowerCase();
  const supabaseAdmin = getSupabaseAdmin();

  const payload = {
    email: normalizedEmail,
    google_id: input.googleId,
    name: input.name ?? null
  };

  const { data, error } = await supabaseAdmin
    .from("users")
    .upsert(payload, { onConflict: "email" })
    .select("id, email, name, google_id, password_hash")
    .single<AuthUserRecord>();

  if (error) {
    throw new Error(`Failed to upsert Google user: ${error.message}`);
  }

  return data;
}

export async function createCredentialsUser(input: {
  email: string;
  name?: string | null;
  passwordHash: string;
}): Promise<AuthUserRecord> {
  const normalizedEmail = input.email.trim().toLowerCase();
  const supabaseAdmin = getSupabaseAdmin();

  const payload = {
    email: normalizedEmail,
    name: input.name ?? null,
    password_hash: input.passwordHash,
    google_id: null
  };

  const { data, error } = await supabaseAdmin
    .from("users")
    .insert(payload)
    .select("id, email, name, google_id, password_hash")
    .single<AuthUserRecord>();

  if (error) {
    throw new Error(`Failed to create user: ${error.message}`);
  }

  return data;
}
