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

// Google subjects identify accounts. An email collision must never change an existing login method.
export async function getOrCreateGoogleUser(
  input: { googleId: string; email: string; name?: string | null; beforeCreate?: () => Promise<void> },
  supabaseAdmin = getSupabaseAdmin()
): Promise<AuthUserRecord | null> {
  const normalizedEmail = input.email.trim().toLowerCase();

  const { data: googleUser, error: googleLookupError } = await supabaseAdmin
    .from("users")
    .select("id, email, name, google_id, password_hash")
    .eq("google_id", input.googleId)
    .maybeSingle<AuthUserRecord>();

  if (googleLookupError) {
    throw new Error(`Failed to load Google user: ${googleLookupError.message}`);
  }
  if (googleUser) {
    return googleUser;
  }

  const { data: emailUser, error: emailLookupError } = await supabaseAdmin
    .from("users")
    .select("id")
    .eq("email", normalizedEmail)
    .maybeSingle();

  if (emailLookupError) {
    throw new Error(`Failed to check Google email: ${emailLookupError.message}`);
  }
  if (emailUser) {
    return null;
  }

  await input.beforeCreate?.();

  const payload = {
    email: normalizedEmail,
    google_id: input.googleId,
    name: input.name ?? null,
    password_hash: null
  };

  const { data, error } = await supabaseAdmin
    .from("users")
    // Unique email and google_id constraints also reject a conflicting concurrent signup.
    .insert(payload)
    .select("id, email, name, google_id, password_hash")
    .single<AuthUserRecord>();

  if (error) {
    throw new Error(`Failed to create Google user: ${error.message}`);
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
