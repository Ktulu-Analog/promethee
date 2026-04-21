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
 * TabModel.tsx — Onglet « Modèle »
 *
 * Configuration du serveur OpenAI-compatible (Albert API).
 *
 * Sections :
 *   - Serveur OpenAI-compatible (API Base, Modèle + refresh)
 *   - Statut de la clé API (saisie dans « Mes clés API »)
 */

import React, { useState, useEffect } from "react";
import { Settings } from "../../hooks/useSettings";
import { Group, FormRow, TextInput, ComboInput } from "./SettingsUI";

interface Props {
  settings: Settings;
  draft: DraftModel;
  onChange: (d: DraftModel) => void;
  fetchModels: (backend: "openai", apiBase?: string, apiKey?: string) => Promise<string[]>;
  /** Callback pour naviguer vers l'onglet « Mes clés API » */
  onNavigateToApiKeys?: () => void;
}

export interface DraftModel {
  OPENAI_API_BASE: string;
  OPENAI_MODEL: string;
}

export function TabModel({ settings, draft, onChange, fetchModels, onNavigateToApiKeys }: Props) {
  const [openaiModels, setOpenaiModels] = useState<string[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    refreshOpenAI(true);
  }, []);

  async function refreshOpenAI(silent = false) {
    const url = draft.OPENAI_API_BASE.trim();
    if (!url) { if (!silent) setMsg("⚠ Saisissez d'abord l'API Base URL"); return; }
    setRefreshing(true);
    setMsg("Chargement…");
    try {
      const models = await fetchModels("openai", url);
      setOpenaiModels(models);
      setMsg(models.length > 0 ? `✓ ${models.length} modèle(s)` : "⚠ Aucun modèle trouvé");
    } catch {
      setMsg("✗ Erreur de connexion");
    } finally {
      setRefreshing(false);
    }
  }

  function set(key: keyof DraftModel, val: string) {
    onChange({ ...draft, [key]: val });
  }

  return (
    <div>
      <Group title="Serveur OpenAI-compatible">
        <FormRow label="API Base URL :">
          <TextInput
            value={draft.OPENAI_API_BASE}
            onChange={(v) => set("OPENAI_API_BASE", v)}
            placeholder="https://albert.api.etalab.gouv.fr/v1"
          />
        </FormRow>

        {/* Statut de la clé API — saisie déplacée vers « Mes clés API » */}
        <FormRow label="Clé API :">
          <div style={s.apiKeyStatus}>
            <span style={settings.OPENAI_API_KEY_SET ? s.statusOk : s.statusMissing}>
              {settings.OPENAI_API_KEY_SET ? "✓ Configurée" : "✗ Non configurée"}
            </span>
            <button
              style={s.linkBtn}
              onClick={onNavigateToApiKeys}
              type="button"
            >
              {settings.OPENAI_API_KEY_SET ? "Modifier dans « Mes clés API »" : "Configurer dans « Mes clés API »"}
            </button>
          </div>
        </FormRow>

        <FormRow label="Modèle :">
          <div>
            <ComboInput
              value={draft.OPENAI_MODEL}
              onChange={(v) => set("OPENAI_MODEL", v)}
              options={openaiModels}
              onRefresh={() => refreshOpenAI(false)}
              refreshing={refreshing}
              placeholder="openai/gpt-4o"
            />
            {msg && <span style={s.hint}>{msg}</span>}
          </div>
        </FormRow>
      </Group>
    </div>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────

const s: Record<string, React.CSSProperties> = {
  apiKeyStatus: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    padding: "6px 0",
  },
  statusOk: {
    fontSize: 12,
    fontWeight: 600,
    color: "#5ab467",
  },
  statusMissing: {
    fontSize: 12,
    fontWeight: 600,
    color: "#e07878",
  },
  linkBtn: {
    background: "none",
    border: "none",
    padding: 0,
    fontSize: 12,
    color: "var(--accent)",
    cursor: "pointer",
    textDecoration: "underline",
    textUnderlineOffset: 2,
  },
  hint: {
    fontSize: 11,
    color: "var(--text-muted)",
    marginTop: 3,
    display: "block",
  },
};
