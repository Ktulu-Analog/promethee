/**
 * ============================================================================
 * Prométhée — Assistant IA avancé
 * ============================================================================
 * Auteur  : Pierre COUGET ktulu.analog@gmail.com
 * Licence : GNU Affero General Public License v3.0 (AGPL-3.0)
 *           https://www.gnu.org/licenses/agpl-3.0.html
 * Année   : 2026
 * ----------------------------------------------------------------------------
 * Ce fichier fait partie du projet Prométhée.
 * Vous pouvez le redistribuer et/ou le modifier selon les termes de la
 * licence AGPL-3.0 publiée par la Free Software Foundation.
 * ============================================================================
 *
 *
 * useAuth.ts — Gestion de l'authentification JWT
 *
 * Stockage du token en mémoire (variable module) + localStorage pour la
 * persistance entre rechargements.
 *
 * Expose :
 *   - token / user       : état courant
 *   - login()            : POST /auth/login-json → stocke le token
 *   - register()         : POST /auth/register
 *   - logout()           : efface le token
 *   - isAuthenticated    : boolean
 */

import { useState, useEffect, useCallback } from "react";

const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
const TOKEN_KEY = "promethee_token";
const USER_KEY  = "promethee_user";

export interface AuthUser {
  user_id: string;
  username: string;
  is_admin: boolean;
}

// ── Token en module-scope (partagé entre tous les composants sans Context) ───
let _token: string | null = null;

export function getToken(): string | null {
  if (_token) return _token;
  const stored = localStorage.getItem(TOKEN_KEY);
  if (stored) {
    _token = stored;
    return _token;
  }
  return null;
}

function _setToken(t: string | null) {
  _token = t;
  if (t) localStorage.setItem(TOKEN_KEY, t);
  else    localStorage.removeItem(TOKEN_KEY);
}

function _setUser(u: AuthUser | null) {
  if (u) localStorage.setItem(USER_KEY, JSON.stringify(u));
  else    localStorage.removeItem(USER_KEY);
}

function _loadUser(): AuthUser | null {
  try {
    const s = localStorage.getItem(USER_KEY);
    return s ? JSON.parse(s) : null;
  } catch {
    return null;
  }
}

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useAuth() {
  const [token, setTokenState] = useState<string | null>(getToken);
  const [user,  setUserState]  = useState<AuthUser | null>(_loadUser);
  const [error, setError]      = useState<string | null>(null);
  const [loading, setLoading]  = useState(false);

  const isAuthenticated = Boolean(token && user);

  const login = useCallback(async (username: string, password: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${BASE}/auth/login-json`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail ?? "Identifiants incorrects.");
      }
      const data = await res.json();
      const newToken = data.access_token as string;
      const newUser: AuthUser = { user_id: data.user_id, username: data.username, is_admin: Boolean(data.is_admin) };
      _setToken(newToken);
      _setUser(newUser);
      setTokenState(newToken);
      setUserState(newUser);
    } catch (e: any) {
      setError(e.message ?? "Erreur de connexion.");
      throw e;
    } finally {
      setLoading(false);
    }
  }, []);

  const register = useCallback(async (
    username: string,
    email: string,
    password: string,
  ) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${BASE}/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, email, password }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail ?? "Erreur lors de la création du compte.");
      }
      // Auto-login après inscription
      await login(username, password);
    } catch (e: any) {
      setError(e.message ?? "Erreur d'inscription.");
      throw e;
    } finally {
      setLoading(false);
    }
  }, [login]);

  const logout = useCallback(() => {
    _setToken(null);
    _setUser(null);
    setTokenState(null);
    setUserState(null);
  }, []);

  return { token, user, isAuthenticated, error, loading, login, register, logout };
}
