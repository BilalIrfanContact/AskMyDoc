import assert from "node:assert/strict";
import test from "node:test";

import { createClient } from "@supabase/supabase-js";
import NextAuth, { type NextAuthConfig, type User } from "next-auth";
import type { CredentialsConfig } from "next-auth/providers/credentials";
import { encode, type JWT } from "next-auth/jwt";
import { NextRequest } from "next/server";

import { createAuthConfig } from "./auth-config";
import { getOrCreateGoogleUser, type AuthUserRecord } from "./auth-users";
import { hashPassword, verifyPassword } from "./password";

type Callbacks = NonNullable<NextAuthConfig["callbacks"]>;
type SignInInput = Parameters<NonNullable<Callbacks["signIn"]>>[0];
type JwtInput = Parameters<NonNullable<Callbacks["jwt"]>>[0];

function userRecord(overrides: Partial<AuthUserRecord> = {}): AuthUserRecord {
  return {
    id: "credentials-user",
    email: "reader@example.test",
    name: "Reader",
    google_id: null,
    password_hash: "existing-password-hash",
    ...overrides
  };
}

// Use the real Supabase query builder against an in-memory REST endpoint. No external requests.
function userStore(initialUsers: AuthUserRecord[] = []) {
  const users = structuredClone(initialUsers);
  const writes: string[] = [];
  let beforeInsert: (() => void) | undefined;
  const client = createClient("https://supabase.example.test", "test-service-key", {
    auth: { persistSession: false, autoRefreshToken: false },
    global: {
      fetch: async (input, init) => {
        const url = new URL(String(input));
        const method = init?.method ?? "GET";
        assert.equal(url.pathname, "/rest/v1/users");
        const headers = new Headers(init?.headers);
        const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), {
          status,
          headers: { "content-type": "application/json" }
        });

        if (method === "GET") {
          const rows = users.filter((user) => [...url.searchParams].every(([key, value]) => {
            if (key === "select" || key === "limit") return true;
            assert.ok(value.startsWith("eq."));
            return user[key as keyof AuthUserRecord] === value.slice(3);
          }));
          return json(headers.get("accept")?.includes("vnd.pgrst.object") ? rows[0] ?? null : rows);
        }

        writes.push(method);
        assert.equal(method, "POST", "Login must never update an existing user");
        const payload = JSON.parse(String(init?.body)) as Partial<AuthUserRecord>;
        beforeInsert?.();
        beforeInsert = undefined;
        const existing = users.find((user) => user.email === payload.email || (
          payload.google_id && user.google_id === payload.google_id
        ));
        if (existing) {
          // Model the old unsafe upsert too, so the regression fails against the original behavior.
          if (headers.get("prefer")?.includes("resolution=merge-duplicates")) {
            Object.assign(existing, payload);
            return json(existing);
          }
          return json({ code: "23505", message: "duplicate user" }, 409);
        }

        const created = userRecord({
          id: `user-${users.length + 1}`,
          password_hash: null,
          ...payload
        });
        users.push(created);
        return json(created, 201);
      }
    }
  });
  const config = createAuthConfig({
    getUserByEmail: async (email) => users.find((user) => user.email === email.trim().toLowerCase()) ?? null,
    getOrCreateGoogleUser: (input) => getOrCreateGoogleUser(input, client),
    verifyPassword
  });
  const credentials = config.providers.find((provider) => (
    typeof provider !== "function" && provider.id === "credentials"
  )) as CredentialsConfig & { options: Partial<CredentialsConfig> };
  assert.ok(credentials.options?.authorize);

  return {
    users,
    writes,
    config,
    callbacks: config.callbacks,
    googleLogin: (input = googleInput()) => config.callbacks.signIn(input),
    passwordLogin: (password: string) => credentials.options!.authorize!(
      { email: "reader@example.test", password }, new Request("https://askmydoc.example.test/login")
    ),
    raceInsert: (callback: () => void) => { beforeInsert = callback; }
  };
}

function googleInput(overrides: Partial<SignInInput> = {}): SignInInput {
  return {
    user: { id: "google-subject", email: "reader@example.test", name: "Reader" },
    account: { provider: "google", type: "oidc", providerAccountId: "google-subject" },
    profile: { sub: "google-subject", email: "reader@example.test", email_verified: true },
    ...overrides
  };
}

function sessionInput(token: JWT, extra: Partial<JwtInput> = {}): JwtInput {
  // Auth.js omits user on session reads even though its published callback type requires it.
  return { token, user: undefined as unknown as User, ...extra };
}

test("an unverified signup cannot be merged into the email owner's Google account", async () => {
  const store = userStore([userRecord()]);
  const before = structuredClone(store.users);
  const input = googleInput();

  assert.equal(await store.googleLogin(input), false);
  assert.equal(input.user.id, "google-subject");
  assert.deepEqual(store.users, before);
  assert.deepEqual(store.writes, []);
});

test("a new verified Google account has its own user ID and no password", async () => {
  const store = userStore();
  const input = googleInput();

  assert.equal(await store.googleLogin(input), true);
  assert.equal(input.user.id, store.users[0].id);
  assert.notEqual(input.user.id, "google-subject");
  assert.equal(store.users[0].google_id, "google-subject");
  assert.equal(store.users[0].password_hash, null);
  const token = await store.callbacks.jwt({ token: {}, user: input.user, account: input.account });
  assert.equal(token?.userId, store.users[0].id);
});

test("returning Google login uses the subject even when its email changes", async () => {
  const store = userStore([userRecord({ id: "google-user", google_id: "google-subject", password_hash: null })]);
  const input = googleInput({
    user: { id: "google-subject", email: "new-address@example.test" },
    profile: { sub: "google-subject", email: "new-address@example.test", email_verified: true }
  });

  assert.equal(await store.googleLogin(input), true);
  assert.equal(input.user.id, "google-user");
  assert.equal(store.users.length, 1);
  assert.deepEqual(store.writes, []);
});

test("a different Google subject cannot replace the account with the same email", async () => {
  const store = userStore([userRecord({ google_id: "original-google-subject", password_hash: null })]);
  const before = structuredClone(store.users);

  assert.equal(await store.googleLogin(), false);
  assert.deepEqual(store.users, before);
  assert.deepEqual(store.writes, []);
});

test("unverified or missing Google email verification is denied before any write", async () => {
  for (const emailVerified of [false, undefined, "true"]) {
    const store = userStore();
    assert.equal(await store.googleLogin(googleInput({
      // Exercise malformed provider data too, beyond Auth.js's declared boolean type.
      profile: { sub: "google-subject", email: "reader@example.test", email_verified: emailVerified } as SignInInput["profile"]
    })), false);
    assert.deepEqual(store.users, []);
    assert.deepEqual(store.writes, []);
  }
});

test("Google login fails closed when the provider identity or profile email is missing", async () => {
  const store = userStore();
  const inputs = [
    googleInput({ account: { provider: "google", type: "oidc", providerAccountId: "" } }),
    googleInput({ profile: { sub: "google-subject", email_verified: true } }),
    googleInput({ profile: { sub: "different-subject", email: "reader@example.test", email_verified: true } })
  ];
  for (const input of inputs) assert.equal(await store.googleLogin(input), false);
  assert.deepEqual(store.writes, []);
});

test("a signup racing Google login cannot acquire its Google identity", async () => {
  const store = userStore();
  store.raceInsert(() => { store.users.push(userRecord()); });

  await assert.rejects(store.googleLogin(), /duplicate user/);
  assert.equal(store.users.length, 1);
  assert.equal(store.users[0].google_id, null);
  assert.equal(store.users[0].password_hash, "existing-password-hash");
});

test("existing password accounts still sign in with the correct password", async () => {
  const passwordHash = await hashPassword("correct-password");
  const store = userStore([userRecord({ password_hash: passwordHash })]);

  assert.equal((await store.passwordLogin("correct-password"))?.id, "credentials-user");
  assert.equal(await store.passwordLogin("wrong-password"), null);
});

test("a legacy merged account cannot be accessed using its old password", async () => {
  const passwordHash = await hashPassword("attacker-password");
  const store = userStore([userRecord({ google_id: "google-subject", password_hash: passwordHash })]);

  assert.equal(await store.passwordLogin("attacker-password"), null);
  const input = googleInput();
  assert.equal(await store.googleLogin(input), true);
  assert.equal(input.user.id, "credentials-user");
});

test("sessions issued before the fix expire instead of retaining access", async () => {
  const store = userStore([userRecord()]);
  assert.equal(await store.callbacks.jwt(sessionInput({ userId: "credentials-user", email: "reader@example.test" })), null);
  assert.equal(await store.callbacks.jwt(sessionInput({ email: "reader@example.test" })), null);
});

test("new sessions retain the authenticated database ID and ignore client identity updates", async () => {
  const store = userStore();
  const token = await store.callbacks.jwt({ token: {}, user: { id: "authenticated-user", name: "Reader" } });
  assert.ok(token);
  const refreshed = await store.callbacks.jwt(sessionInput(token, {
    trigger: "update", session: { userId: "another-user", email: "another@example.test" }
  }));
  assert.equal(refreshed?.userId, "authenticated-user");
  assert.deepEqual(store.writes, []);
});

test("a new Google account uses the verified profile email and normalizes it", async () => {
  const store = userStore();
  const input = googleInput({
    user: { id: "google-subject", email: "untrusted@example.test" },
    profile: { sub: "google-subject", email: " Reader@Example.Test ", email_verified: true }
  });
  assert.equal(await store.googleLogin(input), true);
  assert.equal(store.users[0].email, "reader@example.test");
  assert.equal(input.user.email, "reader@example.test");
});

test("Auth.js rejects and clears a real encrypted session cookie issued before the fix", async () => {
  const store = userStore([userRecord()]);
  const secret = "isolated-test-secret-for-encrypted-session-cookies";
  const token = await encode({
    token: { userId: "credentials-user", email: "reader@example.test" },
    secret,
    salt: "authjs.session-token"
  });
  const { handlers } = NextAuth({ ...store.config, secret, trustHost: true });
  const response = await handlers.GET(new NextRequest("http://localhost:3000/api/auth/session", {
    headers: { cookie: `authjs.session-token=${token}` }
  }));

  assert.equal(response.status, 200);
  assert.equal(await response.json(), null);
  assert.match(response.headers.get("set-cookie") ?? "", /authjs\.session-token=;.*Max-Age=0/);
});

test("Auth.js exposes the database identity for a new Google session", async () => {
  const store = userStore();
  const input = googleInput();
  assert.equal(await store.googleLogin(input), true);
  const token = await store.callbacks.jwt({ token: {}, user: input.user, account: input.account });
  assert.ok(token);
  const secret = "isolated-test-secret-for-encrypted-session-cookies";
  const encrypted = await encode({ token, secret, salt: "authjs.session-token" });
  const { handlers } = NextAuth({ ...store.config, secret, trustHost: true });
  const response = await handlers.GET(new NextRequest("http://localhost:3000/api/auth/session", {
    headers: { cookie: `authjs.session-token=${encrypted}` }
  }));

  assert.equal(response.status, 200);
  const session = await response.json();
  assert.equal(session.user.id, store.users[0].id);
  assert.equal(session.user.name, "Reader");
});
