"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { signIn } from "next-auth/react";
import { useRouter } from "next/navigation";
import AuthDocumentArtwork from "./AuthDocumentArtwork";

export default function SignupForm() {
  const router = useRouter();

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
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
      <main className="auth-layout">
        <section className="auth-story" aria-labelledby="auth-story-title">
          <Link href="/login" className="auth-wordmark">AskMyDoc</Link>
          <div className="auth-story-copy">
            <h1 id="auth-story-title">Keep the document.<br />Find the answer.</h1>
          </div>
          <AuthDocumentArtwork />
          <p className="auth-story-note">Ask questions of 10-Ks, 10-Qs and annual reports.</p>
        </section>

        <section className="auth-panel" aria-labelledby="signup-heading">
          <div className="auth-card auth-card-signup">
          <h2 id="signup-heading">Create your account</h2>
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
              <span className="password-input-wrap">
                <input
                type={showPassword ? "text" : "password"}
                className="input-text"
                autoComplete="new-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="At least 8 characters"
                minLength={8}
                required
                />
                <button type="button" onClick={() => setShowPassword((value) => !value)} aria-label={showPassword ? "Hide passwords" : "Show passwords"}>
                  <EyeIcon />
                </button>
              </span>
              <span className="field-helper">At least 8 characters</span>
            </label>

            <label className="auth-field">
              <span className="text-label">Confirm password</span>
              <span className="password-input-wrap">
                <input
                type={showPassword ? "text" : "password"}
                className="input-text"
                autoComplete="new-password"
                value={confirmPassword}
                onChange={(event) => setConfirmPassword(event.target.value)}
                placeholder="Repeat password"
                minLength={8}
                required
                />
                <button type="button" onClick={() => setShowPassword((value) => !value)} aria-label={showPassword ? "Hide passwords" : "Show passwords"}>
                  <EyeIcon />
                </button>
              </span>
            </label>

            {error ? <p className="auth-error">{error}</p> : null}

            <button type="submit" className="button-primary auth-submit" disabled={loading}>
              {loading ? "Creating account…" : "Create account"}
            </button>
          </form>

          <p className="auth-note">
            Already have an account? <Link href="/login">Sign in</Link>
          </p>
          <p className="auth-privacy"><LockIcon />Your documents stay private to your account.</p>
          </div>
        </section>
      </main>
    </div>
  );
}

function EyeIcon() {
  return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12Z" /><circle cx="12" cy="12" r="2.5" /></svg>;
}

function LockIcon() {
  return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><rect x="5" y="10" width="14" height="11" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3" /></svg>;
}
