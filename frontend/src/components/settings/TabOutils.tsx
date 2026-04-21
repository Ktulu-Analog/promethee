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
 * TabOutils.tsx — Onglet « Outils »
 *
 * Portage de _make_tools_tab() dans settings_dialog.py.
 *
 * Pour chaque famille d'outils enregistrée :
 *   - Badge avec icône + nom + nombre d'outils
 *   - Sélecteur de backend (modèle principal / OpenAI / Ollama)
 *   - ComboInput modèle éditable + bouton refresh
 *   - Champ Base URL optionnel
 *
 * La liste est dynamique : construite depuis GET /tools/families,
 * identique à tools_engine.list_families() en Qt.
 */

import React, { useState } from "react";
import { Family } from "../../hooks/useSettings";
import { Group, FormRow, Select, ComboInput, TextInput, Hint } from "./SettingsUI";

interface Props {
  families: Family[];
  drafts: Record<string, DraftFamily>;
  onChange: (family: string, d: DraftFamily) => void;
  fetchModels: (backend: "openai", apiBase?: string, apiKey?: string) => Promise<string[]>;
}

export interface DraftFamily {
  model_backend: string;
  model_name: string;
  model_base_url: string;
}

const BACKEND_OPTIONS = [
  { value: "",       label: "(modèle principal)" },
  { value: "openai", label: "🌐 OpenAI-compatible" },
];

export function TabOutils({ families, drafts, onChange, fetchModels }: Props) {
  const [modelCache, setModelCache] = useState<Record<string, string[]>>({});
  const [refreshing, setRefreshing] = useState<Record<string, boolean>>({});

  async function doRefresh(family: string, draft: DraftFamily) {
    const url = draft.model_base_url.trim();
    setRefreshing((r) => ({ ...r, [family]: true }));
    try {
      const models = await fetchModels(
        "openai",
        url || undefined,
      );
      setModelCache((c) => ({ ...c, [family]: models }));
    } catch {}
    setRefreshing((r) => ({ ...r, [family]: false }));
  }

  return (
    <div>
      <Hint>
        Assignez optionnellement un modèle LLM dédié à chaque famille d'outils.
        Laisser le champ Modèle vide = le modèle principal est utilisé pour la réponse finale.
      </Hint>

      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {families.map((fam) => {
          const draft = drafts[fam.family] ?? {
            model_backend: fam.model_backend,
            model_name: fam.model_name,
            model_base_url: fam.model_base_url,
          };
          const models = modelCache[fam.family] ?? [];
          const isRefreshing = refreshing[fam.family] ?? false;
          const hasModel = draft.model_backend !== "";

          return (
            <Group
              key={fam.family}
              title={`${fam.icon}  ${fam.label}  (${fam.tool_count} outil${fam.tool_count > 1 ? "s" : ""})`}
            >
              <FormRow label="Backend :">
                <Select
                  value={draft.model_backend}
                  onChange={(v) => onChange(fam.family, { ...draft, model_backend: v, model_name: v ? draft.model_name : "" })}
                  options={BACKEND_OPTIONS}
                />
              </FormRow>

              {hasModel && (
                <>
                  <FormRow label="Modèle :">
                    <ComboInput
                      value={draft.model_name}
                      onChange={(v) => onChange(fam.family, { ...draft, model_name: v })}
                      options={models}
                      onRefresh={() => doRefresh(fam.family, draft)}
                      refreshing={isRefreshing}
                      placeholder="(vide = modèle principal)"
                    />
                  </FormRow>
                  <FormRow label="Base URL :" hint="Vide = hérite de l'endpoint principal">
                    <TextInput
                      value={draft.model_base_url}
                      onChange={(v) => onChange(fam.family, { ...draft, model_base_url: v })}
                      placeholder="https://… ou http://localhost:11434"
                    />
                  </FormRow>
                </>
              )}
            </Group>
          );
        })}

        {families.length === 0 && (
          <p style={{ color: "var(--text-muted)", fontSize: 13, textAlign: "center", padding: 20 }}>
            Aucune famille d'outils enregistrée.
          </p>
        )}
      </div>
    </div>
  );
}
