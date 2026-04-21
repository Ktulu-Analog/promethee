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
 * TabSysteme.tsx — Onglet « Système »
 * TabRag.tsx      — Onglet « RAG »
 * TabInterface.tsx — Onglet « Interface »
 *
 * Portages de _make_system_tab(), _make_rag_tab(), _make_interface_tab()
 * dans settings_dialog.py.
 */

import React, { useState, useEffect, useCallback } from "react";
import { Settings } from "../../hooks/useSettings";
import { Group, FormRow, TextInput, Select, NumberInput, Toggle, StatusDot, Hint } from "./SettingsUI";
import { api } from "../../lib/api";

// ══════════════════════════════════════════════════════════════════
//  Onglet Système
// ══════════════════════════════════════════════════════════════════

export interface DraftSysteme {
  APP_USER: string;
  AGENT_MAX_ITERATIONS: number;
  MAX_CONTEXT_TOKENS: number;
  CONTEXT_HISTORY_MAX_TOKENS: number;
  LTM_MODEL: string;
  LTM_ENABLED: boolean;
}

interface SystemeProps {
  settings: Settings;
  draft: DraftSysteme;
  onChange: (d: DraftSysteme) => void;
}

export function TabSysteme({ settings, draft, onChange }: SystemeProps) {
  function set<K extends keyof DraftSysteme>(key: K, val: DraftSysteme[K]) {
    onChange({ ...draft, [key]: val });
  }

  return (
    <div>
      <Group title="Utilisateur">
        <FormRow label="Nom :" hint="Affiché dans l'interface">
          <TextInput
            value={draft.APP_USER}
            onChange={(v) => set("APP_USER", v)}
            placeholder="Votre nom"
          />
        </FormRow>
      </Group>

      <Group title="Boucle agent">
        <FormRow label="Max itérations :" hint="Limite de la boucle agent (défaut : 8)">
          <NumberInput
            value={draft.AGENT_MAX_ITERATIONS}
            onChange={(v) => set("AGENT_MAX_ITERATIONS", v)}
            min={1} max={40}
          />
        </FormRow>
        <FormRow label="Max tokens contexte :" hint="Tokens max par appel LLM (défaut : 8000)">
          <NumberInput
            value={draft.MAX_CONTEXT_TOKENS}
            onChange={(v) => set("MAX_CONTEXT_TOKENS", v)}
            min={1000} max={200000} step={1000}
          />
        </FormRow>
        <FormRow label="Historique max (tokens) :" hint="Fenêtre glissante de l'historique (défaut : 100 000)">
          <NumberInput
            value={draft.CONTEXT_HISTORY_MAX_TOKENS}
            onChange={(v) => set("CONTEXT_HISTORY_MAX_TOKENS", v)}
            min={10000} max={500000} step={5000}
          />
        </FormRow>
      </Group>

      <Group title="Mémoire long terme (LTM)">
        <FormRow label="Activée :">
          <Toggle
            value={draft.LTM_ENABLED}
            onChange={(v) => set("LTM_ENABLED", v)}
            label={draft.LTM_ENABLED ? "Oui" : "Non"}
          />
        </FormRow>
        {draft.LTM_ENABLED && (
          <FormRow label="Modèle LTM :" hint="Modèle utilisé pour indexer/rappeler la mémoire">
            <TextInput
              value={draft.LTM_MODEL}
              onChange={(v) => set("LTM_MODEL", v)}
              placeholder="mistralai/Mistral-Small-3.2-24B-Instruct-2506"
            />
          </FormRow>
        )}
      </Group>

      <DangerZone />
    </div>
  );
}

// ── Zone de danger : suppression de données ───────────────────────────────────

function DangerZone() {
  const [convStatus, setConvStatus] = useState<"idle" | "confirm" | "loading" | "done">("idle");
  const [ltmStatus, setLtmStatus]   = useState<"idle" | "confirm" | "loading" | "done">("idle");
  const [convResult, setConvResult] = useState<string>("");
  const [ltmResult,  setLtmResult]  = useState<string>("");

  // ── Supprimer toutes les conversations ──────────────────────────────────────
  const handleDeleteAllConvs = useCallback(async () => {
    if (convStatus === "idle") { setConvStatus("confirm"); return; }
    if (convStatus !== "confirm") return;
    setConvStatus("loading");
    try {
      const r = await api.delete<{ deleted: number }>("/conversations");
      setConvResult(`${r.deleted} conversation${r.deleted > 1 ? "s" : ""} supprimée${r.deleted > 1 ? "s" : ""}.`);
      setConvStatus("done");
      // Notifier le sidebar pour qu'il rafraîchisse sa liste immédiatement
      window.dispatchEvent(new CustomEvent("promethee:conversations-cleared"));
    } catch {
      setConvResult("Erreur lors de la suppression.");
      setConvStatus("idle");
    }
  }, [convStatus]);

  // ── Vider la LTM ─────────────────────────────────────────────────────────
  const handleClearLtm = useCallback(async () => {
    if (ltmStatus === "idle") { setLtmStatus("confirm"); return; }
    if (ltmStatus !== "confirm") return;
    setLtmStatus("loading");
    try {
      const r = await api.delete<{ chunks_deleted: number }>("/rag/ltm");
      const n = r.chunks_deleted;
      setLtmResult(`LTM vidée${n > 0 ? ` (${n} souvenir${n > 1 ? "s" : ""} supprimé${n > 1 ? "s" : ""})` : ""}.`);
      setLtmStatus("done");
    } catch {
      setLtmResult("Erreur lors de la suppression.");
      setLtmStatus("idle");
    }
  }, [ltmStatus]);

  const btnBase: React.CSSProperties = {
    padding: "6px 14px",
    borderRadius: 6,
    border: "none",
    fontSize: 12,
    fontWeight: 600,
    cursor: "pointer",
    fontFamily: "inherit",
    transition: "background 0.15s",
  };

  const btnDanger: React.CSSProperties = {
    ...btnBase,
    background: "rgba(220, 80, 80, 0.15)",
    color: "#e07878",
    border: "1px solid rgba(220, 80, 80, 0.35)",
  };

  const btnConfirm: React.CSSProperties = {
    ...btnBase,
    background: "rgba(220, 80, 80, 0.85)",
    color: "#fff",
  };

  const btnCancel: React.CSSProperties = {
    ...btnBase,
    background: "var(--elevated-bg)",
    color: "var(--text-muted)",
    border: "1px solid var(--border)",
    marginLeft: 6,
  };

  const rowStyle: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: 8,
    flexWrap: "wrap",
  };

  const statusStyle: React.CSSProperties = {
    fontSize: 11,
    color: "var(--text-muted)",
    fontStyle: "italic",
  };

  return (
    <Group title="🗑️ Données">
      <Hint>Ces actions sont irréversibles.</Hint>

      {/* Supprimer toutes les conversations */}
      <FormRow label="Conversations :">
        <div style={rowStyle}>
          {convStatus === "done" ? (
            <>
              <span style={{ ...statusStyle, color: "var(--accent)" }}>✓ {convResult}</span>
              <button style={btnCancel} onClick={() => { setConvStatus("idle"); setConvResult(""); }}>
                OK
              </button>
            </>
          ) : convStatus === "loading" ? (
            <span style={statusStyle}>Suppression en cours…</span>
          ) : convStatus === "confirm" ? (
            <>
              <span style={statusStyle}>Confirmer la suppression de toutes les conversations ?</span>
              <button style={btnConfirm} onClick={handleDeleteAllConvs}>Confirmer</button>
              <button style={btnCancel}  onClick={() => setConvStatus("idle")}>Annuler</button>
            </>
          ) : (
            <button style={btnDanger} onClick={handleDeleteAllConvs}>
              Supprimer toutes les conversations
            </button>
          )}
        </div>
      </FormRow>

      {/* Vider la LTM */}
      <FormRow label="Mémoire long terme :">
        <div style={rowStyle}>
          {ltmStatus === "done" ? (
            <>
              <span style={{ ...statusStyle, color: "var(--accent)" }}>✓ {ltmResult}</span>
              <button style={btnCancel} onClick={() => { setLtmStatus("idle"); setLtmResult(""); }}>
                OK
              </button>
            </>
          ) : ltmStatus === "loading" ? (
            <span style={statusStyle}>Suppression en cours…</span>
          ) : ltmStatus === "confirm" ? (
            <>
              <span style={statusStyle}>Vider entièrement la mémoire long terme ?</span>
              <button style={btnConfirm} onClick={handleClearLtm}>Confirmer</button>
              <button style={btnCancel}  onClick={() => setLtmStatus("idle")}>Annuler</button>
            </>
          ) : (
            <button style={btnDanger} onClick={handleClearLtm}>
              Vider la mémoire long terme
            </button>
          )}
        </div>
      </FormRow>
    </Group>
  );
}

// ══════════════════════════════════════════════════════════════════
//  Onglet RAG
// ══════════════════════════════════════════════════════════════════

export interface DraftRag {
  QDRANT_URL: string;
  QDRANT_COLLECTION: string;
  EMBEDDING_MODE: string;
  EMBEDDING_MODEL: string;
  EMBEDDING_API_BASE: string;
  EMBEDDING_DIMENSION: number;
  RAG_TOP_K: number;
  RAG_MIN_SCORE: number;
  RAG_RERANK_ENABLED: boolean;
}

interface RagProps {
  settings: Settings;
  draft: DraftRag;
  onChange: (d: DraftRag) => void;
}

export function TabRag({ settings, draft, onChange }: RagProps) {
  const [qdrantOk, setQdrantOk] = useState<boolean | null>(null);

  // Vérifie la disponibilité de Qdrant
  useEffect(() => {
    api.get<{ available: boolean }>("/rag/status")
      .then((r) => setQdrantOk(r.available))
      .catch(() => setQdrantOk(false));
  }, []);

  function set<K extends keyof DraftRag>(key: K, val: DraftRag[K]) {
    onChange({ ...draft, [key]: val });
  }

  return (
    <div>
      <Group title="Qdrant">
        <FormRow label="URL :">
          <TextInput
            value={draft.QDRANT_URL}
            onChange={(v) => set("QDRANT_URL", v)}
            placeholder="http://localhost:6333"
          />
        </FormRow>
        <FormRow label="Collection :">
          <TextInput
            value={draft.QDRANT_COLLECTION}
            onChange={(v) => set("QDRANT_COLLECTION", v)}
            placeholder="promethee_docs"
          />
        </FormRow>
        {qdrantOk !== null && (
          <StatusDot
            ok={qdrantOk}
            label={qdrantOk ? "Qdrant disponible" : "Qdrant non disponible"}
          />
        )}
      </Group>

      <Group title="Embeddings">
        <FormRow label="Mode :">
          <Select
            value={draft.EMBEDDING_MODE as "api" | "local"}
            onChange={(v) => set("EMBEDDING_MODE", v)}
            options={[
              { value: "api",   label: "API (OpenAI-compatible)" },
              { value: "local", label: "Local (sentence-transformers)" },
            ]}
          />
        </FormRow>
        <FormRow label="Modèle :">
          <TextInput
            value={draft.EMBEDDING_MODEL}
            onChange={(v) => set("EMBEDDING_MODEL", v)}
            placeholder="BAAI/bge-m3"
          />
        </FormRow>
        {draft.EMBEDDING_MODE === "api" && (
          <FormRow label="API Base :">
            <TextInput
              value={draft.EMBEDDING_API_BASE}
              onChange={(v) => set("EMBEDDING_API_BASE", v)}
              placeholder="https://albert.api.etalab.gouv.fr/v1"
            />
          </FormRow>
        )}
        <FormRow label="Dimension :">
          <NumberInput
            value={draft.EMBEDDING_DIMENSION}
            onChange={(v) => set("EMBEDDING_DIMENSION", v)}
            min={64} max={4096} step={64}
          />
        </FormRow>
      </Group>

      <Group title="Recherche">
        <FormRow label="Top K :" hint="Nombre de chunks récupérés (défaut : 25)">
          <NumberInput
            value={draft.RAG_TOP_K}
            onChange={(v) => set("RAG_TOP_K", v)}
            min={1} max={100}
          />
        </FormRow>
        <FormRow label="Score minimum :" hint="Seuil de similarité (0.0 – 1.0)">
          <NumberInput
            value={draft.RAG_MIN_SCORE}
            onChange={(v) => set("RAG_MIN_SCORE", v)}
            min={0} max={1} step={0.05}
          />
        </FormRow>
        <FormRow label="Reranking :">
          <Toggle
            value={draft.RAG_RERANK_ENABLED}
            onChange={(v) => set("RAG_RERANK_ENABLED", v)}
            label={draft.RAG_RERANK_ENABLED ? "Activé" : "Désactivé"}
          />
        </FormRow>
      </Group>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════
//  Onglet Interface
// ══════════════════════════════════════════════════════════════════

// Options de police identiques à ThemeManager.FONT_OPTIONS en Qt
const FONT_OPTIONS: { label: string; stack: string }[] = [
  { label: 'Système (défaut)',    stack: '"SF Pro Display","Helvetica Neue","Segoe UI",sans-serif' },
  { label: 'Inter',               stack: '"Inter","Helvetica Neue",sans-serif' },
  { label: 'Roboto',              stack: '"Roboto","Helvetica Neue",sans-serif' },
  { label: 'Source Sans Pro',     stack: '"Source Sans Pro","Helvetica Neue",sans-serif' },
  { label: 'Nunito',              stack: '"Nunito","Helvetica Neue",sans-serif' },
  { label: 'JetBrains Mono',      stack: '"JetBrains Mono","Fira Code","Consolas",monospace' },
  { label: 'Fira Sans',           stack: '"Fira Sans","Helvetica Neue",sans-serif' },
  { label: 'Merriweather',        stack: '"Merriweather","Georgia",serif' },
];

export interface DraftInterface {
  fontLabel: string;
}

interface InterfaceProps {
  draft: DraftInterface;
  onChange: (d: DraftInterface) => void;
}

export function TabInterface({ draft, onChange }: InterfaceProps) {
  const currentFont = FONT_OPTIONS.find((f) => f.label === draft.fontLabel)?.stack
    ?? FONT_OPTIONS[0].stack;
  const previewFirst = currentFont.split(",")[0].replace(/"/g, "").trim();

  return (
    <div>
      <Group title="Police de l'interface">
        <Hint>
          ⚠ Le changement de police est appliqué immédiatement dans l'application.
        </Hint>

        <FormRow label="Police :">
          <select
            value={draft.fontLabel}
            onChange={(e) => {
              const label = e.target.value;
              onChange({ fontLabel: label });
              // Application immédiate (équivalent de QApplication.setFont() en Qt)
              const stack = FONT_OPTIONS.find((f) => f.label === label)?.stack ?? FONT_OPTIONS[0].stack;
              document.documentElement.style.setProperty("--font-family-ui", stack);
              document.body.style.fontFamily = stack;
              localStorage.setItem("promethee_font", label);
            }}
            style={{
              padding: "5px 9px",
              background: "var(--input-bg)",
              border: "1px solid var(--input-border)",
              borderRadius: 6,
              color: "var(--input-color)",
              fontSize: 13,
              width: "100%",
              cursor: "pointer",
            }}
          >
            {FONT_OPTIONS.map((f) => (
              <option key={f.label} value={f.label}>{f.label}</option>
            ))}
          </select>
        </FormRow>

        {/* Aperçu — identique au preview_lbl Qt */}
        <FormRow label="Aperçu :">
          <div
            style={{
              fontFamily: currentFont,
              fontSize: 14,
              color: "var(--text-primary)",
              padding: "6px 0",
              lineHeight: 1.5,
            }}
          >
            La vieille forêt aux branches tordues — 0123456789
          </div>
        </FormRow>
      </Group>
    </div>
  );
}

// ── Helper public : restaurer la police sauvegardée au démarrage ──────────

export function restoreSavedFont() {
  const saved = localStorage.getItem("promethee_font");
  if (!saved) return;
  const found = FONT_OPTIONS.find((f) => f.label === saved);
  if (found) {
    document.documentElement.style.setProperty("--font-family-ui", found.stack);
    document.body.style.fontFamily = found.stack;
  }
}
