import { useEffect, useState } from "react";
import { authClient } from "../lib/authClient";

interface AuthModalProps {
  onClose: () => void;
}

export default function AuthModal({ onClose }: AuthModalProps) {
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  const handleSignIn = async () => {
    setLoading(true);
    setError("");
    const result = await authClient.signIn.email({ email, password });
    setLoading(false);
    if (result.error) {
      setError(result.error.message ?? "Sign in failed.");
    } else {
      onClose();
    }
  };

  const handleSignUp = async () => {
    setLoading(true);
    setError("");
    const result = await authClient.signUp.email({ email, password, name });
    setLoading(false);
    if (result.error) {
      setError(result.error.message ?? "Account creation failed.");
    } else {
      onClose();
    }
  };

  const switchMode = (next: "signin" | "signup") => {
    setMode(next);
    setError("");
  };

  return (
    <div className="auth-modal-backdrop">
      <div className="auth-modal" role="dialog" aria-modal="true" aria-label={mode === "signin" ? "Sign in" : "Create account"}>
        <button
          type="button"
          className="linklike auth-modal-close"
          onClick={onClose}
          aria-label="Close"
        >
          ×
        </button>

        <h2 style={{ marginBottom: "1rem" }}>
          {mode === "signin" ? "Sign in" : "Create account"}
        </h2>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (mode === "signin") {
              if (email && password) void handleSignIn();
            } else if (email && password && name) {
              void handleSignUp();
            }
          }}
        >
          {mode === "signup" && (
            <div className="field">
              <label htmlFor="auth-name">Name</label>
              <input
                id="auth-name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                autoComplete="name"
                disabled={loading}
              />
            </div>
          )}

          <div className="field" style={mode === "signup" ? { marginTop: "0.75rem" } : undefined}>
            <label htmlFor="auth-email">Email</label>
            <input
              id="auth-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              disabled={loading}
            />
          </div>

          <div className="field" style={{ marginTop: "0.75rem" }}>
            <label htmlFor="auth-password">Password</label>
            <input
              id="auth-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={mode === "signin" ? "current-password" : "new-password"}
              disabled={loading}
            />
          </div>

          {error && <p className="field-error" style={{ marginTop: "0.5rem" }}>{error}</p>}

          <div className="actions">
            {mode === "signin" ? (
              <>
                <button type="submit" disabled={loading || !email || !password}>
                  {loading ? "Signing in…" : "Sign in"}
                </button>
                <button
                  type="button"
                  className="linklike"
                  onClick={() => switchMode("signup")}
                >
                  Create account
                </button>
              </>
            ) : (
              <>
                <button type="submit" disabled={loading || !email || !password || !name}>
                  {loading ? "Creating…" : "Create account"}
                </button>
                <button
                  type="button"
                  className="linklike"
                  onClick={() => switchMode("signin")}
                >
                  Sign in instead
                </button>
              </>
            )}
          </div>
        </form>
      </div>
    </div>
  );
}
