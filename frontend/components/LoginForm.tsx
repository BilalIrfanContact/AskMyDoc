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
