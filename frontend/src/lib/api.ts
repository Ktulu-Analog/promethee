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
 * api.ts — Client HTTP typé vers le serveur FastAPI
 *
 * v2 (multi-user) : injecte automatiquement le JWT Bearer dans chaque requête.
 * Le token est lu depuis useAuth.getToken() (module-scope).
 */

import { getToken } from "../hooks/useAuth";

const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function request<T>(
  method: string,
  path: string,
  body?: unknown
): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {};
  if (body) headers["Content-Type"] = "application/json";
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${BASE}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
    credentials: "include",
  });

  if (res.status === 403 && res.headers.get("X-Requires-Unlock")) {
    throw Object.assign(new Error("DB_LOCKED"), { code: "DB_LOCKED" });
  }

  // Token expiré ou invalide
  if (res.status === 401) {
    throw Object.assign(new Error("UNAUTHORIZED"), { code: "UNAUTHORIZED" });
  }

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const json = await res.json();
      detail = json.detail ?? detail;
    } catch {}
    throw new Error(`${res.status} ${detail}`);
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  get:    <T>(path: string)                => request<T>("GET",    path),
  post:   <T>(path: string, body: unknown) => request<T>("POST",   path, body),
  patch:  <T>(path: string, body: unknown) => request<T>("PATCH",  path, body),
  put:    <T>(path: string, body: unknown) => request<T>("PUT",    path, body),
  delete: <T>(path: string)               => request<T>("DELETE", path),
};
