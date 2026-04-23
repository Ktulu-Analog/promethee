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
 * App.tsx — Layout principal de Prométhée
 * Gestion :
 *   - Conversation active (activeConvId)
 *   - Création / suppression de conversations — délégué à ConvSidePanel
 *   - Toggle des panneaux droits (RAG, Monitoring) — RAG pleinement implémenté
 *   - Déverrouillage DB chiffrée (écran UnlockScreen)
 *   - Chargement du modèle actif depuis GET /settings
 */

import React, { useState, useEffect, useCallback, useRef } from "react";
import { ConvSidePanel } from "./components/sidebar/ConvSidePanel";
import { ChatPanel } from "./components/chat/ChatPanel";
import { SettingsDialog } from "./components/settings/SettingsDialog";
import { AdminPanel } from "./components/admin/AdminPanel";
import type { Profile } from "./components/profiles/ProfilesPanel";
import { api } from "./lib/api";
import { useAuth, getToken } from "./hooks/useAuth";
import { LoginScreen } from "./components/auth/LoginScreen";
import { useConversationTree } from "./hooks/useConversationTree";
import "./styles/theme.css";

// ── Types ──────────────────────────────────────────────────────────────────

interface AppState {
  activeConvId: string | null;
  dbLocked: boolean;
  passphrase: string;
  passphraseError: string;
  modelLabel: string;
  familyRouting: { family: string; label: string; model: string } | null;
}

// ── App ───────────────────────────────────────────────────────────────────

export default function App() {
  const { isAuthenticated, user, login, register, logout, error: authError, loading: authLoading } = useAuth();

  const [state, setState] = useState<AppState>({
    activeConvId: null,
    dbLocked: false,
    passphrase: "",
    passphraseError: "",
    modelLabel: "…",
    familyRouting: null,
  });

  const [ragCollection, setRagCollection] = useState<string | null>(null);

  // ── Arbre de conversations (pour passer les actions au ChatPanel) ─────────
  const {
    tree,
    renameConversation,
    starConversation,
    moveConversation,
  } = useConversationTree();

  // ── Chargement de la collection RAG par défaut au démarrage ─────────────
  // Permet à ChatPanel d'avoir une collection dès le premier message,
  // même si l'utilisateur n'a jamais ouvert le panneau RAG.
  useEffect(() => {
    if (!isAuthenticated) return;
    async function loadDefaultCollection() {
      try {
        const res = await fetch(
          `${(import.meta as any).env?.VITE_API_URL ?? "http://localhost:8000"}/rag/collections`,
          { headers: { Authorization: `Bearer ${getToken() ?? ""}` } }
        );
        if (!res.ok) return;
        const cols: { name: string; is_own: boolean }[] = await res.json();
        // Filtrer la collection mémoire long terme
        const visible = cols.filter((c) => !c.name.startsWith("promethee_memory_"));
        if (visible.length === 0) return;
        // Préférer la collection propre à l'utilisateur (★)
        const own = visible.find((c) => c.is_own);
        const def = own ?? visible[0];
        setRagCollection((current) => {
          // Ne pas écraser un choix déjà fait par l'utilisateur
          if (current !== null) return current;
          return def.name;
        });
      } catch {}
    }
    loadDefaultCollection();
  }, [isAuthenticated]);
  const [currentProfile, setCurrentProfile] = useState<Profile | null>(null);
  const [showClearModal, setShowClearModal] = useState(false);
  const clearMessagesRef = useRef<(() => void) | null>(null);

  // ── Démarrage : vérifier verrouillage + charger modèle ───────────────────
  // NOTE : on ne crée plus de conversation ici — c'est ConvSidePanel qui s'en
  // charge via onReady(), appelé une fois son chargement initial terminé.

  // Charger le modèle actif une fois authentifié
  useEffect(() => {
    if (isAuthenticated) {
      loadModelLabel();
    }
  }, [isAuthenticated]);

  async function loadModelLabel() {
    try {
      const settings = await api.get<{
        OPENAI_MODEL: string;
        OLLAMA_MODEL: string;
        LOCAL: boolean;
      }>("/settings");
      const label = settings.LOCAL ? settings.OLLAMA_MODEL : settings.OPENAI_MODEL;
      setState((s) => ({ ...s, modelLabel: label || "Modèle non configuré" }));
    } catch {}
  }

  // ── Déverrouillage DB ────────────────────────────────────────────────────

  async function handleUnlock() {
    if (!state.passphrase) return;
    try {
      await api.post("/auth/unlock", { passphrase: state.passphrase });
      setState((s) => ({ ...s, dbLocked: false, passphrase: "", passphraseError: "" }));
      await loadModelLabel();
    } catch {
      setState((s) => ({ ...s, passphraseError: "Passphrase incorrecte." }));
    }
  }

  // ── Callbacks conversations ───────────────────────────────────────────────

  // Appelé par ConvSidePanel quand l'utilisateur clique sur une conv
  const handleSelectConv = useCallback((id: string) => {
    setState((s) => ({ ...s, activeConvId: id }));
  }, []);

  // Appelé par ConvSidePanel une fois son chargement initial terminé.
  // Il nous passe l'id de la première conv (existante ou fraîchement créée).
  const handleReady = useCallback((firstConvId: string) => {
    setState((s) => ({ ...s, activeConvId: firstConvId }));
  }, []);

  const handleTitleChange = useCallback((_convId: string, _title: string) => {
    // La sidebar se rafraîchit automatiquement via son hook
  }, []);

  // ── Panneaux ─────────────────────────────────────────────────────────────
  const [showSettings, setShowSettings] = useState(false);
  const [showAdmin, setShowAdmin] = useState(false);
  const [adminExists, setAdminExists] = useState<boolean | null>(null);

  // Vérifier si un admin existe (avant connexion, pour le setup initial)
  useEffect(() => {
    const BASE = (import.meta as any).env?.VITE_API_URL ?? "http://localhost:8000";
    fetch(`${BASE}/auth/admin-exists`)
      .then(r => r.json())
      .then(d => setAdminExists(d.exists))
      .catch(() => setAdminExists(true)); // en cas d'erreur, ne pas bloquer
  }, []);

  async function handleSetupAdmin(username: string, email: string, password: string) {
    const BASE = (import.meta as any).env?.VITE_API_URL ?? "http://localhost:8000";
    const res = await fetch(`${BASE}/auth/setup-admin`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, email, password }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail ?? "Erreur lors de la création de l'admin.");
    }
    setAdminExists(true);
    await login(username, password);
  }

  // ── Écran de déverrouillage ───────────────────────────────────────────────

  // Écran de connexion si non authentifié
  if (!isAuthenticated) {
    return (
      <LoginScreen
        onLogin={login}
        onRegister={register}
        onSetupAdmin={handleSetupAdmin}
        adminExists={adminExists ?? true}
        error={authError}
        loading={authLoading}
      />
    );
  }

  // ── Layout principal ──────────────────────────────────────────────────────

  return (
    <div style={s.root}>
      {/* Sidebar — source de vérité pour l'arbre et la conv active */}
      <ConvSidePanel
        activeConvId={state.activeConvId}
        onSelectConv={handleSelectConv}
        onReady={handleReady}
        currentUsername={user?.username}
        onLogout={logout}
        onOpenSettings={() => setShowSettings(true)}
        onOpenAdmin={() => setShowAdmin(true)}
        isAdmin={user?.is_admin ?? false}
        modelLabel={state.modelLabel}
        familyRouting={state.familyRouting}
        currentProfile={currentProfile}
        onProfileChange={setCurrentProfile}
      />

      {/* Zone centrale */}
      <div style={s.main}>
        {state.activeConvId ? (
          <ChatPanel
            key={state.activeConvId}
            convId={state.activeConvId}
            activeModel={state.modelLabel}
            onClearRequest={(fn) => { clearMessagesRef.current = fn; }}
            ragCollection={ragCollection}
            onCollectionChange={(col) => setRagCollection(col)}
            onTitleChange={handleTitleChange}
            onFamilyRouting={(info) =>
              setState((s) => ({ ...s, familyRouting: info }))
            }
            currentProfile={currentProfile}
            onProfileChange={setCurrentProfile}
            username={user?.username}
            folders={[
              ...(tree?.folders ?? []),
              ...Object.keys(tree?.conversations_by_folder ?? {})
                .map(id => tree?.folders.find(f => f.id === id))
                .filter(Boolean) as { id: string; name: string }[],
            ].filter((f, i, arr) => arr.findIndex(x => x.id === f.id) === i)}
            onRenameConv={renameConversation}
            onStarConv={starConversation}
            onMoveConv={moveConversation}
            onClearConv={() => {
              if (!state.activeConvId) return;
              setShowClearModal(true);
            }}
          />
        ) : (
          <div style={s.empty}>
            <p style={{ color: "var(--text-muted)" }}>Chargement…</p>
          </div>
        )}
      </div>

      {/* SettingsDialog */}
      <SettingsDialog
        open={showSettings}
        onClose={() => setShowSettings(false)}
        onSaved={() => loadModelLabel()}
      />

      {/* AdminPanel */}
      <AdminPanel
        open={showAdmin}
        onClose={() => setShowAdmin(false)}
        currentUserId={user?.user_id ?? ""}
      />
      {/* ── Modale confirmation effacement conversation ── */}
      {showClearModal && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.55)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000 }}>
          <div style={{ background: "var(--surface-bg)", border: "1px solid var(--border)", borderRadius: 12, padding: "24px 28px", width: 340, maxWidth: "90vw", boxShadow: "0 20px 60px rgba(0,0,0,0.5)", display: "flex", flexDirection: "column", gap: 16 }}>
            <div style={{ fontWeight: 700, fontSize: 15, color: "var(--text-primary)" }}>🗑️ Effacer la conversation</div>
            <div style={{ fontSize: 13, color: "var(--text-secondary)", lineHeight: 1.5 }}>
              Tous les messages de cette conversation seront supprimés définitivement. Cette action est irréversible.
            </div>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
              <button
                onClick={() => setShowClearModal(false)}
                style={{ padding: "7px 16px", background: "var(--elevated-bg)", border: "1px solid var(--border)", borderRadius: 7, color: "var(--text-primary)", fontSize: 13, cursor: "pointer", fontFamily: "inherit" }}
              >
                Annuler
              </button>
              <button
                onClick={async () => {
                  setShowClearModal(false);
                  if (!state.activeConvId) return;
                  await api.delete(`/conversations/${state.activeConvId}/messages`);
                  clearMessagesRef.current?.();
                }}
                style={{ padding: "7px 16px", background: "#c0392b", border: "none", borderRadius: 7, color: "#fff", fontSize: 13, fontWeight: 700, cursor: "pointer", fontFamily: "inherit" }}
              >
                Effacer
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────

const s: Record<string, React.CSSProperties> = {
  root: {
    display: "flex",
    height: "100vh",
    overflow: "hidden",
    background: "var(--base-bg)",
  },
  main: {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    overflow: "hidden",
    minWidth: 0,
  },
  empty: {
    flex: 1,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  },
  unlockScreen: {
    height: "100vh",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    background: "var(--base-bg)",
  },
  unlockCard: {
    background: "var(--surface-bg)",
    border: "1px solid var(--border)",
    borderRadius: 12,
    padding: "36px 40px",
    width: 360,
    display: "flex",
    flexDirection: "column",
    gap: 12,
  },
  unlockTitle: {
    margin: 0,
    fontSize: 22,
    color: "var(--text-primary)",
    textAlign: "center",
  },
  unlockSubtitle: {
    margin: 0,
    fontSize: 13,
    color: "var(--text-muted)",
    textAlign: "center",
  },
  unlockInput: {
    padding: "9px 12px",
    background: "var(--input-bg)",
    border: "1px solid var(--input-border)",
    borderRadius: 7,
    color: "var(--input-color)",
    fontSize: 14,
    outline: "none",
  },
  unlockError: {
    margin: 0,
    fontSize: 12,
    color: "#e07878",
    textAlign: "center",
  },
  unlockBtn: {
    padding: "9px",
    background: "var(--accent)",
    color: "#fff",
    border: "none",
    borderRadius: 7,
    fontSize: 14,
    fontWeight: 600,
    cursor: "pointer",
  },
};
