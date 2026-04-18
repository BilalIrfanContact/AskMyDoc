"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { signIn } from "next-auth/react";
import { useRouter, useSearchParams } from "next/navigation";

export default function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const callbackUrl = searchParams.get("callbackUrl") || "/";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [credentialsLoading, setCredentialsLoading] = useState(false);
  const [googleLoading, setGoogleLoading] = useState(false);

  const handleCredentialsSignIn = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setCredentialsLoading(true);

    try {
      const result = await signIn("credentials", {
        email,
        password,
        redirect: false,
        callbackUrl
      });

      if (!result || result.error) {
        setError("Invalid email or password.");
        return;
      }

      router.push(result.url || callbackUrl);
      router.refresh();
    } finally {
      setCredentialsLoading(false);
    }
  };

  const handleGoogleSignIn = async () => {
    setError(null);
    setGoogleLoading(true);
    await signIn("google", { callbackUrl });
  };

  return (
    <div className="app-shell auth-shell">
      <main className="shell-grid auth-grid">
        <section className="auth-copy">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '20px', marginBottom: '24px' }}>
            <img src="/logo.png" alt="AskMyDoc Logo" width={80} height={80} />
            <h1 className="hero-title auth-title" style={{ margin: 0 }}>AskMyDoc.</h1>
          </div>
          <p className="text-olive auth-copy-text">Continue with Google or use an existing email and password.</p>
        </section>

        <section className="card-ivory auth-card" aria-label="Login form">
          <form className="auth-form" onSubmit={handleCredentialsSignIn}>
            <label className="auth-field">
              <span className="text-label">Email</span>
              <input
                type="email"
                className="input-text"
                autoComplete="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="you@example.com"
                required
              />
            </label>

            <label className="auth-field">
              <span className="text-label">Password</span>
              <input
                type="password"
                className="input-text"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="Password"
                required
              />
            </label>

            {error ? <p className="auth-error">{error}</p> : null}

            <button type="submit" className="btn-brand auth-submit" disabled={credentialsLoading}>
              {credentialsLoading ? "Signing in..." : "Sign in"}
            </button>
          </form>

          <div className="auth-divider" aria-hidden="true">
            <span />
            <p>or</p>
            <span />
          </div>

          <button type="button" className="btn-white auth-google" onClick={handleGoogleSignIn} disabled={googleLoading}>
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 128 128">
              <path fill="#e33629" d="M44.59 4.21a64 64 0 0 1 42.61.37a61.22 61.22 0 0 1 20.35 12.62c-2 2.14-4.11 4.14-6.15 6.22Q95.58 29.23 89.77 35a34.28 34.28 0 0 0-13.64-8a37.17 37.17 0 0 0-37.46 9.74a39.25 39.25 0 0 0-9.18 14.91L8.76 35.6A63.53 63.53 0 0 1 44.59 4.21z"></path>
              <path fill="#f8bd00" d="M3.26 51.5a62.93 62.93 0 0 1 5.5-15.9l20.73 16.09a38.31 38.31 0 0 0 0 24.63q-10.36 8-20.73 16.08a63.33 63.33 0 0 1-5.5-40.9z"></path>
              <path fill="#587dbd" d="M65.27 52.15h59.52a74.33 74.33 0 0 1-1.61 33.58a57.44 57.44 0 0 1-16 26.26c-6.69-5.22-13.41-10.4-20.1-15.62a29.72 29.72 0 0 0 12.66-19.54H65.27c-.01-8.22 0-16.45 0-24.68z"></path>
              <path fill="#319f43" d="M8.75 92.4q10.37-8 20.73-16.08A39.3 39.3 0 0 0 44 95.74a37.16 37.16 0 0 0 14.08 6.08a41.29 41.29 0 0 0 15.1 0a36.16 36.16 0 0 0 13.93-5.5c6.69 5.22 13.41 10.4 20.1 15.62a57.13 57.13 0 0 1-25.9 13.47a67.6 67.6 0 0 1-32.36-.35a63 63 0 0 1-23-11.59A63.73 63.73 0 0 1 8.75 92.4z"></path>
            </svg>
            {googleLoading ? "Connecting..." : "Continue with Google"}
          </button>

          <p className="auth-note">
            Need an account? <Link href="/signup">Create one</Link>
          </p>
        </section>
      </main>
    </div>
  );
}
