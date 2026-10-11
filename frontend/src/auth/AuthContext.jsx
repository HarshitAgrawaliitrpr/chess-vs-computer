/**
 * Session state for the whole app: who is signed in (email, Google or guest),
 * the bootstrap config (is Google sign-in configured?), and the auth actions.
 *
 * On mount we restore a previous session from localStorage via /me, and fetch
 * /api/auth/config once to learn whether the Google button should render.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { authApi, clearToken, getToken, setToken } from "../api/authClient.js";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [googleClientId, setGoogleClientId] = useState(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const config = await authApi.config();
        if (alive && config && config.google_enabled) setGoogleClientId(config.google_client_id);
      } catch {
        /* optional - the Google button just stays hidden */
      }
      if (getToken()) {
        try {
          const me = await authApi.me();
          if (alive) setUser(me);
        } catch {
          clearToken(); // expired/invalid session
        }
      }
      if (alive) setLoading(false);
    })();
    return () => {
      alive = false;
    };
  }, []);

  const applySession = useCallback((session) => {
    setToken(session.token);
    setUser(session.user);
  }, []);

  const value = useMemo(
    () => ({
      user,
      loading,
      googleClientId,
      async login(credentials) {
        applySession(await authApi.login(credentials));
      },
      async register(fields) {
        applySession(await authApi.register(fields));
      },
      async googleLogin(credential) {
        applySession(await authApi.google(credential));
      },
      async playAsGuest(name) {
        applySession(await authApi.guest(name ? { name } : {}));
      },
      logout() {
        clearToken();
        setUser(null);
      },
    }),
    [user, loading, googleClientId, applySession],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside <AuthProvider>");
  return context;
}
