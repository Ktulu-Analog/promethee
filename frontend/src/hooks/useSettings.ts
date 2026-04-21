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
 * useSettings.ts
 *
 * Charge et mute la configuration complète depuis l'API FastAPI.
 */

import { useState, useEffect, useCallback } from "react";
import { api } from "../lib/api";

// ── Types ──────────────────────────────────────────────────────────────────

export interface Settings {
  APP_TITLE: string;
  APP_VERSION: string;
  APP_USER: string;
  OPENAI_API_BASE: string;
  OPENAI_API_KEY_SET: boolean;
  OPENAI_MODEL: string;
  QDRANT_URL: string;
  RAG_USER_ID: string;
  QDRANT_COLLECTION: string;
  EMBEDDING_MODE: string;
  EMBEDDING_MODEL: string;
  EMBEDDING_API_BASE: string;
  EMBEDDING_DIMENSION: number;
  RAG_TOP_K: number;
  RAG_MIN_SCORE: number;
  RAG_RERANK_ENABLED: boolean;
  AGENT_MAX_ITERATIONS: number;
  MAX_CONTEXT_TOKENS: number;
  CONTEXT_HISTORY_MAX_TOKENS: number;
  DB_ENCRYPTION: boolean;
  LTM_ENABLED: boolean;
  LTM_MODEL: string;
}

export interface Family {
  family: string;
  label: string;
  icon: string;
  enabled: boolean;
  tool_count: number;
  model_backend: string;
  model_name: string;
  model_base_url: string;
}

export interface UseSettingsReturn {
  settings: Settings | null;
  families: Family[];
  loading: boolean;
  saving: boolean;
  error: string | null;
  reload: () => Promise<void>;
  save: (updates: Record<string, string>) => Promise<void>;
  fetchModels: (backend: "openai", apiBase?: string, apiKey?: string) => Promise<string[]>;
  saveFamilies: (updates: { family: string; model_backend: string; model_name: string; model_base_url: string }[]) => Promise<void>;
}

// ── Hook ──────────────────────────────────────────────────────────────────

export function useSettings(): UseSettingsReturn {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [families, setFamilies] = useState<Family[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const [s, f] = await Promise.all([
        api.get<Settings>("/settings"),
        api.get<Family[]>("/tools/families"),
      ]);
      setSettings(s);
      setFamilies(f);
      setError(null);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { reload(); }, []);

  const save = useCallback(async (updates: Record<string, string>) => {
    setSaving(true);
    try {
      await api.patch("/settings", { updates });
      await reload();
    } catch (e: any) {
      setError(e.message);
      throw e;
    } finally {
      setSaving(false);
    }
  }, [reload]);

  const fetchModels = useCallback(async (
    backend: "openai",
    apiBase?: string,
    apiKey?: string,
  ): Promise<string[]> => {
    const params = new URLSearchParams({ backend });
    if (apiBase) params.set("api_base", apiBase);
    if (apiKey)  params.set("api_key",  apiKey);
    const r = await api.get<{ models: string[] }>(`/settings/models?${params}`);
    return r.models;
  }, []);

  const saveFamilies = useCallback(async (
    updates: { family: string; model_backend: string; model_name: string; model_base_url: string }[]
  ) => {
    await Promise.all(
      updates.map((u) =>
        api.patch(`/tools/families/${u.family}`, {
          model_backend:  u.model_backend,
          model_name:     u.model_name,
          model_base_url: u.model_base_url,
        })
      )
    );
    const f = await api.get<Family[]>("/tools/families");
    setFamilies(f);
  }, []);

  return { settings, families, loading, saving, error, reload, save, fetchModels, saveFamilies };
}
