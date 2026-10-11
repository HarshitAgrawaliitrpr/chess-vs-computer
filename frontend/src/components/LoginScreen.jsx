/**
 * Login gate shown until a session exists: Google (Identity Services),
 * email/password sign-in or registration, and one-click guest play.
 *
 * The Google button only renders when the backend reports a configured
 * GOOGLE_CLIENT_ID; otherwise a short note explains how to enable it.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "../auth/AuthContext.jsx";

let googleScriptPromise = null;

function loadGoogleScript() {
  if (window.google?.accounts?.id) return Promise.resolve();
  if (googleScriptPromise) return googleScriptPromise;
  googleScriptPromise = new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = "https://accounts.google.com/gsi/client";
    script.async = true;
    script.defer = true;
    script.onload = () => resolve();
    script.onerror = () => {
      googleScriptPromise = null;
      reject(new Error("Google library failed to load"));
    };
    document.head.appendChild(script);
  });
  return googleScriptPromise;
}

export default function LoginScreen() {
  const { login, register, googleLogin, playAsGuest, googleClientId } = useAuth();
  const [mode, setMode] = useState("signin"); // "signin" | "register"
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const googleButtonRef = useRef(null);

  /** Run an auth action with shared busy/error handling. */
  const withBusy = useCallback((action) => {
    setBusy(true);
    setError("");
    Promise.resolve()
      .then(action)
      .catch((err) => setError(err?.message || "Something went wrong."))
      .finally(() => setBusy(false));
  }, []);

  const handleGoogle = useCallback(
    (credential) => withBusy(() => googleLogin(credential)),
    [googleLogin, withBusy],
  );

  useEffect(() => {
    if (!googleClientId || !googleButtonRef.current) return undefined;
    let cancelled = false;
    loadGoogleScript()
      .then(() => {
        if (cancelled || !googleButtonRef.current || !window.google?.accounts?.id) return;
        window.google.accounts.id.initialize({
          client_id: googleClientId,
          callback: (response) => handleGoogle(response.credential),
        });
        window.google.accounts.id.renderButton(googleButtonRef.current, {
          theme: "outline",
          size: "large",
          width: 260,
          text: "continue_with",
        });
      })
      .catch(() => {
        if (!cancelled) setError("Google sign-in could not be loaded.");
      });
    return () => {
      cancelled = true;
    };
  }, [googleClientId, handleGoogle]);

  const onSubmit = (event) => {
    event.preventDefault();
    withBusy(() =>
      mode === "signin"
        ? login({ email, password })
        : register({ email, name: name || "Player", password }),
    );
  };

  return (
    <div className="login">
      <div className="login__card">
        <h1 className="login__title">Chess vs. Computer</h1>
        <p className="login__subtitle">Sign in to save your games and keep your history.</p>

        {googleClientId ? (
          <div className="login__oauth" ref={googleButtonRef} />
        ) : (
          <p className="login__note">Google sign-in activates once GOOGLE_CLIENT_ID is configured.</p>
        )}

        <div className="login__divider">
          <span>or</span>
        </div>

        <form className="login__form" onSubmit={onSubmit}>
          {mode === "register" && (
            <label className="login__field">
              <span>Display name</span>
              <input
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="e.g. Mia"
                maxLength={60}
              />
            </label>
          )}
          <label className="login__field">
            <span>Email</span>
            <input
              type="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="you@example.com"
              autoComplete="email"
            />
          </label>
          <label className="login__field">
            <span>Password</span>
            <input
              type="password"
              required
              minLength={mode === "register" ? 8 : 1}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder={mode === "register" ? "At least 8 characters" : "Your password"}
              autoComplete={mode === "register" ? "new-password" : "current-password"}
            />
          </label>

          {error && (
            <p className="login__error" role="alert">
              {error}
            </p>
          )}

          <button type="submit" className="login__submit" disabled={busy}>
            {busy ? "Please wait…" : mode === "signin" ? "Sign in" : "Create account"}
          </button>
        </form>

        <button
          type="button"
          className="login__guest"
          disabled={busy}
          onClick={() => withBusy(() => playAsGuest())}
        >
          Play as guest
        </button>

        <button
          type="button"
          className="login__switch"
          disabled={busy}
          onClick={() => {
            setMode(mode === "signin" ? "register" : "signin");
            setError("");
          }}
        >
          {mode === "signin" ? "New here? Create an account" : "Already have an account? Sign in"}
        </button>

        <p className="login__credit">CREATED BY HARSHIT AGRAWAL WITH MIMO</p>
      </div>
    </div>
  );
}
