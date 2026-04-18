"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { signIn } from "next-auth/react";
import { useRouter } from "next/navigation";

export default function SignupForm() {
  const router = useRouter();

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);

    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setLoading(true);

    try {
      const signupResponse = await fetch("/api/auth/signup", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          name,
          email,
          password
        })
      });

      const signupData = (await signupResponse.json().catch(() => null)) as { error?: string } | null;

      if (!signupResponse.ok) {
        setError(signupData?.error || "Failed to create account.");
        return;
      }

      const loginResult = await signIn("credentials", {
        email,
        password,
        redirect: false,
        callbackUrl: "/"
      });

      if (!loginResult || loginResult.error) {
        setError("Account created, but automatic sign-in failed.");
        router.push("/login");
        return;
      }

      router.push(loginResult.url || "/");
      router.refresh();
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="app-shell auth-shell">
      <main className="shell-grid auth-grid">
        <section className="auth-copy">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '20px', marginBottom: '24px' }}>
            <img src="/logo.png" alt="AskMyDoc Logo" width={80} height={80} />
            <h1 className="hero-title auth-title" style={{ margin: 0 }}>AskMyDoc.</h1>
          </div>
          <p className="text-olive auth-copy-text">Set up email/password access for AskMyDoc.</p>
        </section>

        <section className="card-ivory auth-card" aria-label="Signup form">
          <form className="auth-form" onSubmit={handleSubmit}>
            <label className="auth-field">
              <span className="text-label">Name</span>
              <input
                type="text"
                className="input-text"
                autoComplete="name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="Your name"
              />
            </label>

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
                autoComplete="new-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="At least 8 characters"
                minLength={8}
                required
              />
            </label>

            <label className="auth-field">
              <span className="text-label">Confirm password</span>
              <input
                type="password"
                className="input-text"
                autoComplete="new-password"
                value={confirmPassword}
                onChange={(event) => setConfirmPassword(event.target.value)}
                placeholder="Repeat password"
                minLength={8}
                required
              />
            </label>

            {error ? <p className="auth-error">{error}</p> : null}

            <button type="submit" className="btn-brand auth-submit" disabled={loading}>
              {loading ? "Creating account..." : "Create account"}
            </button>
          </form>

          <p className="auth-note">
            Already have an account? <Link href="/login">Sign in</Link>
          </p>
        </section>
      </main>
    </div>
  );
}
