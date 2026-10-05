import { CredentialsSignin, type NextAuthConfig } from "next-auth";
import { AuthRateLimitError, checkAuthRate } from "./auth-rate-limit";
import Credentials from "next-auth/providers/credentials";
import Google from "next-auth/providers/google";

import { getUserByEmail, getOrCreateGoogleUser } from "./auth-users";
import { verifyPassword } from "./password";

// Expire pre-fix cookies, including any issued to a pre-created or previously merged account.
const AUTH_VERSION = 1;

class RateLimitedLogin extends CredentialsSignin {
  code = "rate_limited";
}

type AuthDependencies = {
  checkAuthRate: typeof checkAuthRate;
  getUserByEmail: typeof getUserByEmail;
  getOrCreateGoogleUser: typeof getOrCreateGoogleUser;
  verifyPassword: typeof verifyPassword;
};

// Tests supply an isolated user store while exercising the production providers and callbacks.
export function createAuthConfig(
  dependencies: AuthDependencies = { getUserByEmail, getOrCreateGoogleUser, verifyPassword, checkAuthRate },
  request?: { headers: Headers }
) {
  return {
    secret: process.env.NEXTAUTH_SECRET,
    session: {
      strategy: "jwt"
    },
    providers: [
      Google({
        clientId: process.env.GOOGLE_CLIENT_ID,
        clientSecret: process.env.GOOGLE_CLIENT_SECRET
      }),
      Credentials({
        name: "Email and Password",
        credentials: {
          email: { label: "Email", type: "email" },
          password: { label: "Password", type: "password" }
        },
        async authorize(credentials, request) {
          try {
            await dependencies.checkAuthRate("login", request.headers);
          } catch (error) {
            if (error instanceof AuthRateLimitError) throw new RateLimitedLogin();
            throw error;
          }
          const email = String(credentials?.email ?? "").trim().toLowerCase();
          const password = String(credentials?.password ?? "");

          if (!email || !password) {
            return null;
          }

          const user = await dependencies.getUserByEmail(email);

          // Old email-based merges retained a password whose owner was never verified.
          if (!user || !user.password_hash || user.google_id) {
            return null;
          }

          const isValid = await dependencies.verifyPassword(password, user.password_hash);
          if (!isValid) {
            return null;
          }

          return {
            id: user.id,
            email: user.email,
            name: user.name
          };
        }
      })
    ],
    pages: {
      signIn: "/login"
    },
    callbacks: {
      async signIn({ user, account, profile }) {
        if (account?.provider !== "google") {
          return true;
        }

        const googleId = account.providerAccountId;
        const email = profile?.email;

        if (
          !googleId || profile?.sub !== googleId ||
          typeof email !== "string" || !email.trim() || profile.email_verified !== true
        ) {
          return false;
        }

        let dbUser;
        try {
          dbUser = await dependencies.getOrCreateGoogleUser({
            googleId,
            email,
            beforeCreate: () => dependencies.checkAuthRate("signup", request?.headers),
            name: user.name ?? profile.name ?? null
          });
        } catch (error) {
          if (error instanceof AuthRateLimitError) return "/login?error=SignupRateLimit";
          throw error;
        }
        if (!dbUser) {
          return false;
        }

        user.id = dbUser.id;
        user.email = dbUser.email;
        user.name = dbUser.name;
        return true;
      },
      async jwt({ token, user }) {
        if (user?.id) {
          token.userId = user.id;
          token.authVersion = AUTH_VERSION;
          token.name = user.name;
        }

        // Never reconstruct identity from an email address or upgrade an old session in place.
        if (token.authVersion !== AUTH_VERSION || !token.userId) {
          return null;
        }
        return token;
      },
      async session({ session, token }) {
        if (session.user) {
          if (token.userId) {
            session.user.id = token.userId;
          }
          if (token.name) {
            session.user.name = token.name;
          }
        }
        return session;
      }
    }
  } satisfies NextAuthConfig;
}
