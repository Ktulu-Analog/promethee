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
 * SettingsDialog.tsx
 *
 * Modal principale « Paramètres » — portage complet de SettingsDialog (Qt).
 *
 * 6 onglets :
 *   Modèle      → TabModel    (backend, URL, modèle + refresh)
 *   Outils      → TabOutils   (famille par famille, modèle assigné)
 *   Système     → TabSysteme  (user, agent, LTM)
 *   RAG         → TabRag      (Qdrant, embeddings, recherche)
 *   Interface   → TabInterface (police)
 *   Mes clés    → TabApiKeys  (clés API personnelles, chiffrées en base)
 *
 * Sauvegarde :
 *   PATCH /settings  { updates: { KEY: value, ... } }
 *     → clés système → .env
 *     → clés personnelles → user_secrets (chiffré AES-256-GCM, par utilisateur)
 *   PATCH /tools/families/{family} pour chaque famille modifiée
 *
 * Note migration : OPENAI_API_KEY n'est plus dans DraftModel ni dans handleSave.
 * La clé passe exclusivement par TabApiKeys → PUT /auth/me/apikeys.
 */

import React, { useState, useEffect, useCallback } from "react";
import { useSettings, Settings } from "../../hooks/useSettings";
import { TabModel, DraftModel } from "./TabModel";
import { TabOutils, DraftFamily } from "./TabOutils";
import { TabSysteme, DraftSysteme, TabRag, DraftRag, TabInterface, DraftInterface } from "./TabsExtra";
import { TabApiKeys } from "./TabApiKeys";

// ── Types ──────────────────────────────────────────────────────────────────

interface Props {
  open: boolean;
  onClose: () => void;
  onSaved?: () => void;
}

// ── Helpers : settings → draft ────────────────────────────────────────────

function initDraftModel(s: Settings): DraftModel {
  return {
    OPENAI_API_BASE: s.OPENAI_API_BASE,
    // OPENAI_API_KEY supprimé — passe par TabApiKeys / user_secrets
    OPENAI_MODEL:    s.OPENAI_MODEL,
  };
}

function initDraftSysteme(s: Settings): DraftSysteme {
  return {
    APP_USER:                    s.APP_USER,
    AGENT_MAX_ITERATIONS:        s.AGENT_MAX_ITERATIONS,
    MAX_CONTEXT_TOKENS:          s.MAX_CONTEXT_TOKENS,
    CONTEXT_HISTORY_MAX_TOKENS:  s.CONTEXT_HISTORY_MAX_TOKENS,
    LTM_MODEL:                   s.LTM_MODEL,
    LTM_ENABLED:                 s.LTM_ENABLED,
  };
}

function initDraftRag(s: Settings): DraftRag {
  return {
    QDRANT_URL:          s.QDRANT_URL,
    QDRANT_COLLECTION:   s.QDRANT_COLLECTION,
    EMBEDDING_MODE:      s.EMBEDDING_MODE,
    EMBEDDING_MODEL:     s.EMBEDDING_MODEL,
    EMBEDDING_API_BASE:  s.EMBEDDING_API_BASE,
    EMBEDDING_DIMENSION: s.EMBEDDING_DIMENSION,
    RAG_TOP_K:           s.RAG_TOP_K,
    RAG_MIN_SCORE:       s.RAG_MIN_SCORE,
    RAG_RERANK_ENABLED:  s.RAG_RERANK_ENABLED,
  };
}

// ── Composant ──────────────────────────────────────────────────────────────

const TABS = ["Modèle", "Outils", "Système", "RAG", "Interface", "Mes clés API"];
const TAB_API_KEYS_INDEX = 5;

export function SettingsDialog({ open, onClose, onSaved }: Props) {
  const { settings, families, loading, saving, reload, save, fetchModels, saveFamilies } =
    useSettings();

  const [activeTab, setActiveTab] = useState(0);
  const [saveError, setSaveError] = useState("");
  const [saveSuccess, setSaveSuccess] = useState(false);

  // Drafts locaux par onglet (initialisés quand settings se charge)
  const [draftModel,     setDraftModel]     = useState<DraftModel | null>(null);
  const [draftSysteme,   setDraftSysteme]   = useState<DraftSysteme | null>(null);
  const [draftRag,       setDraftRag]       = useState<DraftRag | null>(null);
  const [draftInterface, setDraftInterface] = useState<DraftInterface>({
    fontLabel: localStorage.getItem("promethee_font") ?? "Système (défaut)",
  });
  const [draftFamilies, setDraftFamilies] = useState<Record<string, DraftFamily>>({});

  // Initialiser les drafts quand settings est chargé
  useEffect(() => {
    if (!settings) return;
    setDraftModel((prev) => prev ?? initDraftModel(settings));
    setDraftSysteme((prev) => prev ?? initDraftSysteme(settings));
    setDraftRag((prev) => prev ?? initDraftRag(settings));
  }, [settings]);

  // Initialiser les drafts familles
  useEffect(() => {
    if (!families.length) return;
    setDraftFamilies((prev) => {
      const next = { ...prev };
      families.forEach((f) => {
        if (!next[f.family]) {
          next[f.family] = {
            model_backend:  f.model_backend,
            model_name:     f.model_name,
            model_base_url: f.model_base_url,
          };
        }
      });
      return next;
    });
  }, [families]);

  // Recharger si le dialog est rouvert
  useEffect(() => {
    if (open) {
      reload();
      setSaveError("");
      setSaveSuccess(false);
    }
  }, [open]);

  // Fermer avec Escape
  useEffect(() => {
    if (!open) return;
    function handle(e: KeyboardEvent) { if (e.key === "Escape") onClose(); }
    document.addEventListener("keydown", handle);
    return () => document.removeEventListener("keydown", handle);
  }, [open, onClose]);

  // Navigation programmatique vers « Mes clés API » (depuis TabModel)
  const navigateToApiKeys = useCallback(() => {
    setActiveTab(TAB_API_KEYS_INDEX);
  }, []);

  // ── Sauvegarde ─────────────────────────────────────────────────────────

  const handleSave = useCallback(async () => {
    if (!settings || !draftModel || !draftSysteme || !draftRag) return;
    setSaveError("");
    setSaveSuccess(false);

    // Construire le dict de mises à jour (paramètres système uniquement)
    // OPENAI_API_KEY est intentionnellement absent — il passe par TabApiKeys.
    const updates: Record<string, string> = {
      OPENAI_API_BASE:             draftModel.OPENAI_API_BASE,
      OPENAI_MODEL:                draftModel.OPENAI_MODEL,
      APP_USER:                    draftSysteme.APP_USER,
      AGENT_MAX_ITERATIONS:        String(draftSysteme.AGENT_MAX_ITERATIONS),
      MAX_CONTEXT_TOKENS:          String(draftSysteme.MAX_CONTEXT_TOKENS),
      CONTEXT_HISTORY_MAX_TOKENS:  String(draftSysteme.CONTEXT_HISTORY_MAX_TOKENS),
      LTM_MODEL:                   draftSysteme.LTM_MODEL,
      LTM_ENABLED:                 draftSysteme.LTM_ENABLED ? "ON" : "OFF",
      QDRANT_URL:                  draftRag.QDRANT_URL,
      QDRANT_COLLECTION:           draftRag.QDRANT_COLLECTION,
      EMBEDDING_MODE:              draftRag.EMBEDDING_MODE,
      EMBEDDING_MODEL:             draftRag.EMBEDDING_MODEL,
      EMBEDDING_API_BASE:          draftRag.EMBEDDING_API_BASE,
      EMBEDDING_DIMENSION:         String(draftRag.EMBEDDING_DIMENSION),
      RAG_TOP_K:                   String(draftRag.RAG_TOP_K),
      RAG_MIN_SCORE:               String(draftRag.RAG_MIN_SCORE),
      RAG_RERANK_ENABLED:          draftRag.RAG_RERANK_ENABLED ? "ON" : "OFF",
    };

    try {
      // 1. PATCH /settings (système → .env, personnel → user_secrets)
      await save(updates);

      // 2. Familles d'outils
      const familyUpdates = Object.entries(draftFamilies).map(([family, d]) => ({
        family,
        model_backend:  d.model_backend,
        model_name:     d.model_name,
        model_base_url: d.model_base_url,
      }));
      if (familyUpdates.length > 0) await saveFamilies(familyUpdates);

      setSaveSuccess(true);
      setTimeout(() => {
        onSaved?.();
        onClose();
      }, 600);
    } catch (e: any) {
      setSaveError(e.message ?? "Erreur lors de la sauvegarde");
    }
  }, [settings, draftModel, draftSysteme, draftRag, draftFamilies, save, saveFamilies, onSaved, onClose]);

  // ── Rendu ──────────────────────────────────────────────────────────────

  if (!open) return null;

  const isApiKeysTab = activeTab === TAB_API_KEYS_INDEX;

  return (
    <>
      {/* Overlay */}
      <div style={s.overlay} onClick={onClose} />

      {/* Dialog */}
      <div style={s.dialog} role="dialog" aria-modal="true" aria-label="Paramètres">
        {/* En-tête */}
        <div style={s.header}>
          <h2 style={s.title}>Paramètres</h2>
          <button style={s.closeBtn} onClick={onClose} aria-label="Fermer">×</button>
        </div>

        {/* Onglets */}
        <div style={s.tabBar}>
          {TABS.map((tab, i) => (
            <button
              key={tab}
              style={{
                ...s.tabBtn,
                ...(activeTab === i ? s.tabBtnActive : {}),
              }}
              onClick={() => setActiveTab(i)}
            >
              {tab}
            </button>
          ))}
        </div>

        {/* Corps scrollable */}
        <div style={s.body}>
          {loading || !settings || !draftModel || !draftSysteme || !draftRag ? (
            <div style={s.loadingMsg}>Chargement…</div>
          ) : (
            <>
              {activeTab === 0 && (
                <TabModel
                  settings={settings}
                  draft={draftModel}
                  onChange={setDraftModel}
                  fetchModels={fetchModels}
                  onNavigateToApiKeys={navigateToApiKeys}
                />
              )}
              {activeTab === 1 && (
                <TabOutils
                  families={families}
                  drafts={draftFamilies}
                  onChange={(family, d) =>
                    setDraftFamilies((prev) => ({ ...prev, [family]: d }))
                  }
                  fetchModels={fetchModels}
                />
              )}
              {activeTab === 2 && (
                <TabSysteme
                  settings={settings}
                  draft={draftSysteme}
                  onChange={setDraftSysteme}
                />
              )}
              {activeTab === 3 && (
                <TabRag
                  settings={settings}
                  draft={draftRag}
                  onChange={setDraftRag}
                />
              )}
              {activeTab === 4 && (
                <TabInterface
                  draft={draftInterface}
                  onChange={setDraftInterface}
                />
              )}
              {activeTab === 5 && (
                <TabApiKeys />
              )}
            </>
          )}
        </div>

        {/* Pied de page — masqué sur l'onglet « Mes clés API » (gère sa propre sauvegarde) */}
        <div style={s.footer}>
          {saveError && <span style={s.errorMsg}>{saveError}</span>}
          {saveSuccess && <span style={s.successMsg}>✓ Enregistré</span>}
          <div style={{ flex: 1 }} />
          {!isApiKeysTab && (
            <button style={s.cancelBtn} onClick={onClose} disabled={saving}>
              Annuler
            </button>
          )}
          {!isApiKeysTab && (
            <button
              style={{ ...s.saveBtn, opacity: saving ? 0.7 : 1 }}
              onClick={handleSave}
              disabled={saving || loading}
            >
              {saving ? "Enregistrement…" : "Enregistrer"}
            </button>
          )}
        </div>
      </div>
    </>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────

const s: Record<string, React.CSSProperties> = {
  overlay: {
    position: "fixed",
    inset: 0,
    background: "rgba(0,0,0,0.55)",
    zIndex: 900,
  },
  dialog: {
    position: "fixed",
    top: "50%",
    left: "50%",
    transform: "translate(-50%, -50%)",
    zIndex: 901,
    width: 580,
    maxWidth: "calc(100vw - 32px)",
    maxHeight: "calc(100vh - 48px)",
    background: "var(--surface-bg)",
    border: "1px solid var(--border)",
    borderRadius: 12,
    display: "flex",
    flexDirection: "column",
    boxShadow: "0 20px 60px rgba(0,0,0,0.4)",
    overflow: "hidden",
  },
  header: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "16px 20px 0",
    flexShrink: 0,
  },
  title: {
    margin: 0,
    fontSize: 17,
    fontWeight: 700,
    color: "var(--text-primary)",
  },
  closeBtn: {
    background: "none",
    border: "none",
    fontSize: 22,
    lineHeight: 1,
    color: "var(--text-muted)",
    cursor: "pointer",
    padding: "0 4px",
  },
  tabBar: {
    display: "flex",
    padding: "12px 20px 0",
    gap: 3,
    borderBottom: "1px solid var(--border)",
    flexShrink: 0,
    flexWrap: "wrap",
  },
  tabBtn: {
    background: "var(--elevated-bg)",
    border: "1px solid var(--border)",
    borderBottom: "none",
    borderRadius: "6px 6px 0 0",
    padding: "6px 14px",
    fontSize: 13,
    color: "var(--text-muted)",
    cursor: "pointer",
    transition: "color 0.12s, background 0.12s",
    marginBottom: -1,
  },
  tabBtnActive: {
    background: "var(--surface-bg)",
    color: "var(--text-primary)",
    fontWeight: 600,
    borderColor: "var(--border)",
    borderBottomColor: "var(--surface-bg)",
  },
  body: {
    flex: 1,
    overflowY: "auto",
    padding: "16px 20px",
    minHeight: 0,
  },
  loadingMsg: {
    color: "var(--text-muted)",
    fontSize: 13,
    textAlign: "center",
    padding: 24,
  },
  footer: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    padding: "12px 20px 16px",
    borderTop: "1px solid var(--border)",
    flexShrink: 0,
  },
  errorMsg: {
    fontSize: 12,
    color: "#e07878",
    flex: 1,
  },
  successMsg: {
    fontSize: 12,
    color: "var(--rag-badge-on)",
    flex: 1,
  },
  cancelBtn: {
    padding: "7px 18px",
    background: "var(--elevated-bg)",
    border: "1px solid var(--input-border)",
    borderRadius: 7,
    color: "var(--text-secondary)",
    fontSize: 13,
    cursor: "pointer",
  },
  saveBtn: {
    padding: "7px 22px",
    background: "var(--accent)",
    border: "none",
    borderRadius: 7,
    color: "#fff",
    fontSize: 13,
    fontWeight: 600,
    cursor: "pointer",
  },
};
