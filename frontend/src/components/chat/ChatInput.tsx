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
 * ChatInput.tsx — Barre de saisie complète
 *
 *
 * Fonctionnalités :
 *   ─ Textarea auto-resize, Entrée=envoyer, Maj+Entrée=newline, ↑↓=historique
 *   ─ Drag & drop de fichiers / images
 *   ─ Pièces jointes (📎 fichier, 🖼 image)
 *   ─ Mode Agent + slider itérations + toggle "Ne pas compresser"
 *   ─ Badge outils actifs
 *   ─ Badge RAG cliquable
 *   ─ Sélecteur de profil (GET /profiles)
 *   ─ Pill compound Rôle : label actif + chevron ▾ → menu déroulant inline
 *   ─ Synchronisation du profil actif avec la sidebar via externalProfile prop
 *   ─ Bouton ⏹ Stop pendant la génération
 *   ─ Barre de statut
 *   ─ Toggle masquer/afficher la barre
 *   ─ Infobulles CSS riches sur tous les contrôles
 */

import React, {
  useRef,
  useState,
  useCallback,
  useEffect,
  KeyboardEvent,
  DragEvent,
  ChangeEvent,
} from "react";
import { getToken } from "../../hooks/useAuth";

const BASE = (import.meta as any).env?.VITE_API_URL ?? "http://localhost:8000";

function authFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const token = getToken();
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string> ?? {}),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  return fetch(url, { ...options, headers });
}

// ── Types partagés ─────────────────────────────────────────────────────────

export interface AttachmentItem {
  id: string;
  type: "file" | "image" | "url";
  name: string;
  content?: string;
  base64?: string;
  mimeType?: string;
  url?: string;
}

export interface Profile {
  name: string;
  prompt: string;
  tool_families?: { enabled: string[]; disabled: string[] };
  pinned_skills?: string[];
  is_personal?: boolean;
}

export interface Skill {
  slug: string;
  name: string;
  description?: string;
  tags?: string[];
  version?: string;
  size?: number;
}

// ── Types collections RAG ─────────────────────────────────────────────────

interface RagCollectionOption {
  label: string;
  value: string;
}

interface Props {
  onSend: (text: string, attachments: AttachmentItem[], profileName: string | null, profileIsPersonal: boolean) => void;
  onCancel: () => void;
  isGenerating: boolean;
  ragEnabled: boolean;
  onToggleRag: () => void;
  ragAvailable: boolean;
  ragCollection?: string | null;
  onCollectionChange?: (collection: string) => void;
  agentMode: boolean;
  onToggleAgent: (v: boolean) => void;
  maxIterations: number;
  onIterationsChange: (v: number) => void;
  disableContextManagement: boolean;
  onToggleContextManagement: (v: boolean) => void;
  activeToolCount: number;
  statusMessage: string;
  externalProfile?: Profile | null;
  onProfileChange?: (profile: Profile | null) => void;
}

const MAX_HISTORY = 100;

// ═══════════════════════════════════════════════════════════════════════════
// Tooltip — infobulle CSS légère, sans dépendance externe
// ═══════════════════════════════════════════════════════════════════════════
//
// Usage :
//   <Tooltip content="Texte court" detail="Ligne de détail optionnelle">
//     <button>…</button>
//   </Tooltip>
//
// • Apparaît 500 ms après le survol (annulé si la souris repart).
// • Se positionne au-dessus par défaut, bascule en dessous si pas assez de place.
// • "detail" est affiché en italique atténué sous le texte principal.

interface TooltipProps {
  content: string;
  detail?: string;
  children: React.ReactElement;
}

function Tooltip({ content, detail, children }: TooltipProps) {
  const [visible, setVisible] = useState(false);
  const [above, setAbove] = useState(true);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const wrapRef  = useRef<HTMLDivElement>(null);
  const tipRef   = useRef<HTMLDivElement>(null);

  const show = () => {
    timerRef.current = setTimeout(() => {
      // Décide si l'infobulle passe au-dessus ou en dessous
      if (wrapRef.current) {
        const rect = wrapRef.current.getBoundingClientRect();
        setAbove(rect.top > 90); // au-dessus si assez d'espace
      }
      setVisible(true);
    }, 500);
  };

  const hide = () => {
    if (timerRef.current) clearTimeout(timerRef.current);
    setVisible(false);
  };

  return (
    <div
      ref={wrapRef}
      style={{ position: "relative", display: "inline-flex" }}
      onMouseEnter={show}
      onMouseLeave={hide}
      onFocus={show}
      onBlur={hide}
    >
      {children}
      {visible && (
        <div
          ref={tipRef}
          role="tooltip"
          style={{
            position: "absolute",
            [above ? "bottom" : "top"]: "calc(100% + 8px)",
            left: "50%",
            transform: "translateX(-50%)",
            background: "var(--elevated-bg)",
            border: "1px solid var(--border-active)",
            borderRadius: 7,
            padding: "6px 10px",
            boxShadow: "0 4px 16px rgba(0,0,0,0.35)",
            zIndex: 9999,
            whiteSpace: "nowrap",
            pointerEvents: "none",
            display: "flex",
            flexDirection: "column",
            gap: 2,
            // Petite flèche CSS
            ["--tip-arrow" as any]: above ? "100%" : "auto",
          }}
        >
          {/* Flèche */}
          <div style={{
            position: "absolute",
            [above ? "top" : "bottom"]: "100%",
            left: "50%",
            transform: "translateX(-50%)",
            width: 0,
            height: 0,
            borderLeft: "5px solid transparent",
            borderRight: "5px solid transparent",
            ...(above
              ? { borderBottom: "5px solid var(--border-active)" }
              : { borderTop: "5px solid var(--border-active)" }),
          }} />
          <span style={{ fontSize: 12, color: "var(--text-primary)", fontWeight: 500 }}>
            {content}
          </span>
          {detail && (
            <span style={{ fontSize: 11, color: "var(--text-muted)", fontStyle: "italic" }}>
              {detail}
            </span>
          )}
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// ChatInput — composant principal
// ═══════════════════════════════════════════════════════════════════════════

export function ChatInput({
  onSend,
  onCancel,
  isGenerating,
  ragEnabled,
  onToggleRag,
  ragAvailable,
  ragCollection = null,
  onCollectionChange,
  agentMode,
  onToggleAgent,
  maxIterations,
  onIterationsChange,
  disableContextManagement,
  onToggleContextManagement,
  activeToolCount,
  statusMessage,
  externalProfile,
  onProfileChange,
}: Props) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const imageInputRef = useRef<HTMLInputElement>(null);
  const historyRef = useRef<string[]>([]);

  const [text, setText] = useState("");
  const [attachments, setAttachments] = useState<AttachmentItem[]>([]);
  const [historyIdx, setHistoryIdx] = useState(-1);
  const [savedText, setSavedText] = useState("");
  const [isDraggingOver, setIsDraggingOver] = useState(false);
  const [inputHidden, setInputHidden] = useState(false);
  const [attachMenuOpen, setAttachMenuOpen] = useState(false);
  const [profileMenuOpen, setProfileMenuOpen] = useState(false);

  // Collections RAG — chargées quand le RAG est disponible
  const [ragCollections, setRagCollections] = useState<RagCollectionOption[]>([]);
  const [ragMenuOpen, setRagMenuOpen] = useState(false);

  // Profils — état local, synchronisé avec le profil externe (sidebar)
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [currentProfile, setCurrentProfileState] = useState<Profile | null>(null);

  // Synchro profil externe → état local
  useEffect(() => {
    if (externalProfile !== undefined) {
      setCurrentProfileState(externalProfile);
    }
  }, [externalProfile]);

  // Wrapper qui met à jour l'état local ET notifie le parent
  function setCurrentProfile(profile: Profile | null) {
    setCurrentProfileState(profile);
    onProfileChange?.(profile);
  }

  // Charger les collections RAG quand disponible
  useEffect(() => {
    if (!ragAvailable) return;
    async function loadCollections() {
      try {
        const items: RagCollectionOption[] = [];
        // Qdrant
        const res = await authFetch(`${BASE}/rag/collections`);
        if (res.ok) {
          const cols: { name: string; is_own: boolean }[] = await res.json();
          for (const col of cols) {
            if (col.name.startsWith("promethee_memory_")) continue;
            items.push({ label: col.is_own ? `💾 ${col.name} ★` : `💾 ${col.name}`, value: col.name });
          }
        }
        // Albert
        const resAlbert = await authFetch(`${BASE}/rag/albert/collections`);
        if (resAlbert.ok) {
          const cols: { id: string; name: string; visibility?: string }[] = await resAlbert.json();
          for (const col of cols) {
            const vis = col.visibility === "public" ? "🌐" : "🔒";
            items.push({ label: `⚡${vis} ${col.name}`, value: `albert:${col.id}` });
          }
        }
        setRagCollections(items);
      } catch {}
    }
    loadCollections();
  }, [ragAvailable]);

  // Fermer les menus au clic extérieur
  useEffect(() => {
    function close(e: MouseEvent) {
      const target = e.target as HTMLElement;
      if (!target.closest("[data-attach-menu]")) setAttachMenuOpen(false);
      if (!target.closest("[data-profile-menu]")) setProfileMenuOpen(false);
      if (!target.closest("[data-rag-menu]")) setRagMenuOpen(false);
    }
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  // Charger les profils au montage
  useEffect(() => {
    fetchProfiles();
  }, []);

  async function fetchProfiles() {
    try {
      const [sysRes, perRes] = await Promise.all([
        authFetch(`${BASE}/profiles`),
        authFetch(`${BASE}/personal-profiles`),
      ]);
      const sysData: Profile[] = sysRes.ok ? await sysRes.json() : [];
      const perData: Profile[] = perRes.ok ? await perRes.json() : [];
      const combined = [
        ...sysData,
        ...perData.map((p) => ({ ...p, is_personal: true })),
      ];
      setProfiles(combined);
      if (combined.length > 0 && !currentProfile) {
        const noRole = combined.find((p) => p.name === "Aucun rôle") ?? combined[0];
        setCurrentProfile(noRole);
      }
    } catch {}
  }

  // ── Envoi ──────────────────────────────────────────────────────────────

  const handleSend = useCallback(() => {
    const trimmed = text.trim();
    if (!trimmed && attachments.length === 0) return;
    if (isGenerating) return;

    if (trimmed) {
      historyRef.current = [trimmed, ...historyRef.current].slice(0, MAX_HISTORY);
    }
    setHistoryIdx(-1);
    setSavedText("");

    const profileName = currentProfile?.name ?? null;
    const profileIsPersonal = currentProfile?.is_personal ?? false;
    onSend(trimmed, attachments, profileName, profileIsPersonal);
    setText("");
    setAttachments([]);

    // Reset textarea height
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
    textareaRef.current?.focus();
  }, [text, attachments, isGenerating, onSend, currentProfile]);

  // ── Clavier ────────────────────────────────────────────────────────────

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
      return;
    }
    if (e.key === "ArrowUp" && !e.shiftKey) {
      const hist = historyRef.current;
      if (!hist.length) return;
      if (historyIdx === -1) setSavedText(text);
      const next = Math.min(historyIdx + 1, hist.length - 1);
      setHistoryIdx(next);
      setText(hist[next]);
      e.preventDefault();
      return;
    }
    if (e.key === "ArrowDown" && !e.shiftKey) {
      if (historyIdx <= 0) {
        setHistoryIdx(-1);
        setText(historyIdx === 0 ? savedText : "");
        return;
      }
      const next = historyIdx - 1;
      setHistoryIdx(next);
      setText(historyRef.current[next]);
      e.preventDefault();
    }
  }

  function handleChange(e: ChangeEvent<HTMLTextAreaElement>) {
    setText(e.target.value);
    setHistoryIdx(-1);
    const el = textareaRef.current;
    if (el) {
      el.style.height = "auto";
      el.style.height = Math.min(el.scrollHeight, 160) + "px";
    }
  }

  // ── Drag & drop ────────────────────────────────────────────────────────

  function handleDragOver(e: DragEvent) { e.preventDefault(); setIsDraggingOver(true); }
  function handleDragLeave() { setIsDraggingOver(false); }
  function handleDrop(e: DragEvent) {
    e.preventDefault();
    setIsDraggingOver(false);
    Array.from(e.dataTransfer.files).forEach(processFile);
  }

  // ── Fichiers ───────────────────────────────────────────────────────────

  function processFile(file: File) {
    if (file.type.startsWith("image/")) {
      _uploadToServer(file);
    } else {
      _uploadToServer(file);
    }
  }

  async function _uploadToServer(file: File) {
    const formData = new FormData();
    formData.append("file", file);
    try {
      const res = await authFetch(`${BASE}/upload/file`, {
        method: "POST",
        body: formData,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        console.error("[upload] erreur serveur :", err.detail);
        return;
      }
      const data = await res.json();
      addAttachment({
        id: Math.random().toString(36).slice(2),
        type: data.type,
        name: data.name,
        content: data.content,
        base64: data.base64,
        mimeType: data.mime_type,
      });
    } catch (e) {
      console.error("[upload] fetch échoué :", e);
    }
  }

  function addAttachment(att: AttachmentItem) {
    setAttachments((prev) => [...prev, att]);
  }

  function handleFileInput(e: ChangeEvent<HTMLInputElement>) {
    Array.from(e.target.files ?? []).forEach(processFile);
    e.target.value = "";
  }

  // ── Profil ────────────────────────────────────────────────────────────

  function handleProfileSelect(e: ChangeEvent<HTMLSelectElement>) {
    const selected = profiles.find((p) => p.name === e.target.value) ?? null;
    setCurrentProfile(selected);
  }

  // ── Rendu ──────────────────────────────────────────────────────────────

  const ragColor = ragEnabled
    ? "var(--rag-badge-on)"
    : ragAvailable
      ? "var(--rag-badge-off)"
      : "var(--text-disabled)";

  const canSend = (text.trim().length > 0 || attachments.length > 0) && !isGenerating;

  return (
    <>
      <div style={s.root}>
        {/* ── Zone centrale max-width ───────────────────────────────── */}
        <div style={s.wrap}>

          {/* ── Barre de statut ───────────────────────────────────── */}
          {statusMessage && (
            <div style={s.statusBar}>{statusMessage}</div>
          )}

          {/* ── Pièces jointes ────────────────────────────────────── */}
          {attachments.length > 0 && (
            <div style={s.attachBar}>
              {attachments.map((att) => (
                <div key={att.id} style={s.attachItem}>
                  <span style={s.attachIcon}>{att.type === "image" ? "🖼" : "📄"}</span>
                  <span style={s.attachName}>{att.name}</span>
                  <button
                    style={s.attachRemove}
                    onClick={() => setAttachments((prev) => prev.filter((a) => a.id !== att.id))}
                    title="Retirer"
                  >×</button>
                </div>
              ))}
            </div>
          )}

          {/* ── Boîte de saisie principale ────────────────────────── */}
          <div
            style={{ ...s.box, ...(isDraggingOver ? s.boxDrag : {}) }}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
          >
            {/* Textarea */}
            <textarea
              ref={textareaRef}
              value={text}
              onChange={handleChange}
              onKeyDown={handleKeyDown}
              placeholder={isDraggingOver ? "Déposez ici…" : "Envoyer un message…"}
              rows={1}
              style={s.textarea}
              disabled={isGenerating}
            />

            {/* ── Rangée basse : outils gauche + bouton envoi droite ── */}
            <div style={s.boxFooter}>

              {/* Gauche : attachement + options */}
              <div style={s.footerLeft}>

                {/* Bouton attachement */}
                <div style={{ position: "relative" }} data-attach-menu>
                  <Tooltip
                    content="Joindre un fichier ou une image"
                    detail="Glisser-déposer aussi supporté"
                  >
                    <button
                      style={s.iconBtn}
                      onClick={() => setAttachMenuOpen((v) => !v)}
                    >
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/>
                      </svg>
                    </button>
                  </Tooltip>
                  {attachMenuOpen && (
                    <div style={s.attachMenu}>
                      <button style={s.attachMenuItem} onClick={() => { fileInputRef.current?.click(); setAttachMenuOpen(false); }}>
                        📄 Fichier
                      </button>
                      <button style={s.attachMenuItem} onClick={() => { imageInputRef.current?.click(); setAttachMenuOpen(false); }}>
                        🖼 Image
                      </button>
                    </div>
                  )}
                </div>

                <input ref={fileInputRef} type="file" multiple style={{ display: "none" }} onChange={handleFileInput} />
                <input ref={imageInputRef} type="file" accept="image/*" multiple style={{ display: "none" }} onChange={handleFileInput} />

                {/* Rôle — pill compound : label cliquable + chevron ▾ */}
                <div style={{ position: "relative", display: "inline-flex", alignItems: "center" }} data-profile-menu>
                  {/* Partie gauche : affiche le rôle actif, clic = "Aucun rôle" (reset) */}
                  <Tooltip
                    content={currentProfile && currentProfile.name !== "Aucun rôle" ? `Rôle actif : ${currentProfile.name}` : "Aucun rôle actif"}
                    detail="Cliquez pour réinitialiser · ▾ pour choisir un rôle"
                  >
                    <button
                      style={{
                        ...s.pillBtn,
                        ...(currentProfile && currentProfile.name !== "Aucun rôle" ? s.pillBtnActive : {}),
                        borderRight: "none",
                        borderRadius: "20px 0 0 20px",
                      }}
                      onClick={() => {
                        const noRole = profiles.find((p) => p.name === "Aucun rôle") ?? null;
                        setCurrentProfile(noRole);
                        setProfileMenuOpen(false);
                      }}
                    >
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                        <circle cx="12" cy="8" r="4"/><path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"/>
                      </svg>
                      <span style={{ maxWidth: 90, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {currentProfile && currentProfile.name !== "Aucun rôle" ? `${currentProfile.is_personal ? "🧑 " : ""}${currentProfile.name}` : "Rôle"}
                      </span>
                    </button>
                  </Tooltip>

                  {/* Partie droite : chevron ▾ — ouvre le menu */}
                  <Tooltip content="Choisir un rôle">
                    <button
                      style={{
                        ...s.pillBtn,
                        ...(currentProfile && currentProfile.name !== "Aucun rôle" ? s.pillBtnActive : {}),
                        borderLeft: currentProfile && currentProfile.name !== "Aucun rôle"
                          ? "1px solid rgba(212,129,61,0.35)"
                          : "1px solid var(--border)",
                        borderRadius: "0 20px 20px 0",
                        padding: "4px 7px",
                        gap: 0,
                      }}
                      onClick={() => { setProfileMenuOpen((v) => !v); setAttachMenuOpen(false); setRagMenuOpen(false); }}
                    >
                      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
                        style={{ transform: profileMenuOpen ? "rotate(180deg)" : "none", transition: "transform 0.15s" }}>
                        <polyline points="6 9 12 15 18 9"/>
                      </svg>
                    </button>
                  </Tooltip>

                  {/* Menu déroulant des rôles */}
                  {profileMenuOpen && (
                    <div style={s.profileMenu}>
                      {/* Profils personnels */}
                      {profiles.some((p) => p.is_personal) && (
                        <div style={s.profileMenuHeader}>Mes profils</div>
                      )}
                      {profiles.filter((p) => p.is_personal).map((p) => (
                        <button
                          key={`personal:${p.name}`}
                          style={{
                            ...s.profileMenuItem,
                            ...(currentProfile?.name === p.name && currentProfile?.is_personal ? s.profileMenuItemActive : {}),
                          }}
                          onClick={() => { setCurrentProfile(p); setProfileMenuOpen(false); }}
                        >
                          {currentProfile?.name === p.name && currentProfile?.is_personal && (
                            <span style={{ color: "var(--accent)", flexShrink: 0 }}>✓</span>
                          )}
                          <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            🧑 {p.name}
                          </span>
                        </button>
                      ))}
                      {/* Profils système */}
                      <div style={s.profileMenuHeader}>Rôle système</div>
                      {profiles.filter((p) => !p.is_personal).length === 0 && (
                        <div style={s.profileMenuEmpty}>Aucun profil disponible</div>
                      )}
                      {profiles.filter((p) => !p.is_personal).map((p) => (
                        <button
                          key={`system:${p.name}`}
                          style={{
                            ...s.profileMenuItem,
                            ...(currentProfile?.name === p.name && !currentProfile?.is_personal ? s.profileMenuItemActive : {}),
                          }}
                          onClick={() => { setCurrentProfile(p); setProfileMenuOpen(false); }}
                        >
                          {currentProfile?.name === p.name && !currentProfile?.is_personal && (
                            <span style={{ color: "var(--accent)", flexShrink: 0 }}>✓</span>
                          )}
                          <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            {p.name}
                          </span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>

                {/* Mode Agent */}
                <Tooltip
                  content={agentMode ? "Mode Agent activé" : "Mode Agent désactivé"}
                  detail={
                    agentMode
                      ? `${activeToolCount} outil${activeToolCount !== 1 ? "s" : ""} actif${activeToolCount !== 1 ? "s" : ""} — l'IA peut agir en autonomie`
                      : "Activer pour permettre l'utilisation d'outils"
                  }
                >
                  <button
                    style={{ ...s.pillBtn, ...(agentMode ? s.pillBtnActive : {}) }}
                    onClick={() => onToggleAgent(!agentMode)}
                  >
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                      <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
                    </svg>
                    <span>Agent{agentMode && activeToolCount > 0 ? ` · ${activeToolCount}` : ""}</span>
                  </button>
                </Tooltip>

                {/* RAG — pill + sélecteur de collection intégré */}
                {ragAvailable && (
                  <div style={{ position: "relative", display: "inline-flex", alignItems: "center" }} data-rag-menu>
                    {/* Bouton principal RAG (toggle on/off) */}
                    <Tooltip
                      content={ragEnabled ? "Base documentaire activée" : "Base documentaire désactivée"}
                      detail="Cliquez pour activer/désactiver · ▾ pour choisir la collection"
                    >
                      <button
                        style={{ ...s.pillBtn, ...(ragEnabled ? s.pillBtnRag : {}), borderRight: ragEnabled ? "none" : undefined, borderRadius: ragEnabled ? "20px 0 0 20px" : 20 }}
                        onClick={onToggleRag}
                      >
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
                        </svg>
                        <span>RAG</span>
                      </button>
                    </Tooltip>

                    {/* Bouton chevron — ouvre le sélecteur de collection (visible seulement si RAG actif) */}
                    {ragEnabled && (
                      <Tooltip
                        content="Changer de collection"
                        detail={ragCollection ?? "Aucune collection sélectionnée"}
                      >
                        <button
                          style={{
                            ...s.pillBtn,
                            ...s.pillBtnRag,
                            borderLeft: "1px solid rgba(90,170,122,0.35)",
                            borderRadius: "0 20px 20px 0",
                            padding: "4px 7px",
                            gap: 0,
                          }}
                          onClick={() => setRagMenuOpen((v) => !v)}
                          title="Changer de collection RAG"
                        >
                          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
                            style={{ transform: ragMenuOpen ? "rotate(180deg)" : "none", transition: "transform 0.15s" }}>
                            <polyline points="6 9 12 15 18 9"/>
                          </svg>
                        </button>
                      </Tooltip>
                    )}

                    {/* Menu déroulant des collections */}
                    {ragMenuOpen && ragEnabled && (
                      <div style={s.ragMenu}>
                        <div style={s.ragMenuHeader}>Collection active</div>
                        {ragCollections.length === 0 && (
                          <div style={s.ragMenuEmpty}>Aucune collection disponible</div>
                        )}
                        {ragCollections.map((col) => (
                          <button
                            key={col.value}
                            style={{
                              ...s.ragMenuItem,
                              ...(ragCollection === col.value ? s.ragMenuItemActive : {}),
                            }}
                            onClick={() => {
                              onCollectionChange?.(col.value);
                              setRagMenuOpen(false);
                            }}
                          >
                            {ragCollection === col.value && (
                              <span style={{ color: "var(--rag-badge-on)", flexShrink: 0 }}>✓</span>
                            )}
                            <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                              {col.label}
                            </span>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {/* Itérations agent */}
                {agentMode && (
                  <Tooltip
                    content="Nombre max d'itérations agent"
                    detail="Chaque appel d'outil compte comme une itération. Au-delà de 8, risque de boucle."
                  >
                    <div style={s.iterPill}>
                      <span style={s.iterLabel}>Itérations max</span>
                      <input
                        type="number" min={1} max={40} value={maxIterations}
                        onChange={(e) => onIterationsChange(Number(e.target.value))}
                        style={{
                          ...s.iterInput,
                          ...(maxIterations > 8 ? { color: "var(--warning, #d4813d)" } : {}),
                        }}
                      />
                    </div>
                  </Tooltip>
                )}

                {/* Ne pas compresser le contexte */}
                {agentMode && (
                  <Tooltip
                    content="Désactiver la gestion du contexte"
                    detail="Pas de fenêtre glissante ni de compression — risque de dépasser la fenêtre du modèle"
                  >
                    <button
                      style={{
                        ...s.pillBtn,
                        ...(disableContextManagement ? s.pillBtnWarn : {}),
                      }}
                      onClick={() => onToggleContextManagement(!disableContextManagement)}
                    >
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
                        <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
                      </svg>
                      <span>Pas de compression</span>
                    </button>
                  </Tooltip>
                )}
              </div>

              {/* Droite : compteur + envoi/stop */}
              <div style={s.footerRight}>
                {text.length > 0 && (
                  <Tooltip content="Nombre de caractères saisis">
                    <span style={{ ...s.charCount, cursor: "default" }}>{text.length}</span>
                  </Tooltip>
                )}

                {isGenerating ? (
                  <Tooltip content="Arrêter la génération" detail="Interrompt le stream en cours">
                    <button style={s.stopBtn} onClick={onCancel}>
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                        <rect x="3" y="3" width="18" height="18" rx="2"/>
                      </svg>
                    </button>
                  </Tooltip>
                ) : (
                  <Tooltip content="Envoyer le message" detail="Raccourci : Entrée">
                    <button
                      style={{ ...s.sendBtn, opacity: canSend ? 1 : 0.35 }}
                      onClick={handleSend}
                      disabled={!canSend}
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                        <line x1="12" y1="19" x2="12" y2="5"/><polyline points="5 12 12 5 19 12"/>
                      </svg>
                    </button>
                  </Tooltip>
                )}
              </div>
            </div>
          </div>

          {/* ── Hint clavier ──────────────────────────────────────── */}
          <div style={s.hint}>
            <kbd style={s.kbd}>Entrée</kbd> envoyer &nbsp;·&nbsp; <kbd style={s.kbd}>⇧ Entrée</kbd> saut de ligne &nbsp;·&nbsp; <kbd style={s.kbd}>↑↓</kbd> historique
          </div>
        </div>
      </div>


    </>
  );
}

const s: Record<string, React.CSSProperties> = {
  // ── Conteneur racine ────────────────────────────────────────────────
  root: {
    background: "var(--base-bg)",
    flexShrink: 0,
    padding: "10px 16px 14px",
    display: "flex",
    justifyContent: "center",
    width: "100%",
    boxSizing: "border-box" as const,
  },

  // ── Colonne centrale (largeur fixe, centrée) ────────────────────────
  wrap: {
    width: 740,
    maxWidth: "100%",
    flexShrink: 0,
    display: "flex",
    flexDirection: "column",
    gap: 6,
  },

  // ── Boîte principale ────────────────────────────────────────────────
  box: {
    background: "var(--elevated-bg)",
    border: "1px solid var(--input-border)",
    borderRadius: 14,
    display: "flex",
    flexDirection: "column",
    transition: "border-color 0.15s, box-shadow 0.15s",
    boxShadow: "0 2px 12px rgba(0,0,0,0.18)",
  },
  boxDrag: {
    borderColor: "var(--accent)",
    boxShadow: "0 0 0 3px rgba(212,129,61,0.15)",
  },

  // ── Textarea ────────────────────────────────────────────────────────
  textarea: {
    flex: 1,
    resize: "none",
    background: "transparent",
    border: "none",
    outline: "none",
    color: "var(--input-color)",
    fontSize: 14,
    lineHeight: 1.6,
    fontFamily: "inherit",
    minHeight: 44,
    maxHeight: 200,
    overflowY: "auto",
    padding: "12px 14px 6px",
  },

  // ── Rangée basse de la boîte ────────────────────────────────────────
  boxFooter: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "6px 10px 8px",
    gap: 6,
  },
  footerLeft: {
    display: "flex",
    alignItems: "center",
    gap: 4,
    flexWrap: "wrap",
    flex: 1,
    minWidth: 0,
  },
  footerRight: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    flexShrink: 0,
  },

  // ── Bouton icône neutre (attachement) ───────────────────────────────
  iconBtn: {
    background: "none",
    border: "none",
    cursor: "pointer",
    color: "var(--text-muted)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    width: 30,
    height: 30,
    borderRadius: 7,
    transition: "background 0.12s, color 0.12s",
    flexShrink: 0,
  },

  // ── Pill buttons (profil, agent, RAG) ───────────────────────────────
  pillBtn: {
    display: "flex",
    alignItems: "center",
    gap: 5,
    padding: "4px 9px",
    background: "none",
    border: "1px solid var(--border)",
    borderRadius: 20,
    color: "var(--text-muted)",
    fontSize: 11,
    fontWeight: 500,
    cursor: "pointer",
    fontFamily: "inherit",
    transition: "background 0.12s, border-color 0.12s, color 0.12s",
    whiteSpace: "nowrap",
    height: 26,
  },
  pillBtnActive: {
    background: "rgba(212,129,61,0.12)",
    borderColor: "var(--accent)",
    color: "var(--accent)",
  },
  pillBtnRag: {
    background: "rgba(90,170,122,0.12)",
    borderColor: "var(--rag-badge-on)",
    color: "var(--rag-badge-on)",
  },
  pillBtnWarn: {
    background: "rgba(224,120,120,0.12)",
    borderColor: "#e07878",
    color: "#e07878",
  },

  // ── Itérations inline ───────────────────────────────────────────────
  iterPill: {
    display: "flex",
    alignItems: "center",
    gap: 4,
    padding: "3px 8px",
    background: "none",
    border: "1px solid var(--border)",
    borderRadius: 20,
    height: 26,
    cursor: "default",
  },
  iterLabel: {
    fontSize: 11,
    color: "var(--text-muted)",
    fontFamily: "inherit",
  },
  iterInput: {
    width: 34,
    background: "transparent",
    border: "none",
    outline: "none",
    color: "var(--text-primary)",
    fontSize: 11,
    fontWeight: 600,
    textAlign: "center",
    padding: 0,
    fontFamily: "inherit",
  },

  // ── Compteur caractères ─────────────────────────────────────────────
  charCount: {
    fontSize: 11,
    color: "var(--text-disabled)",
    fontVariantNumeric: "tabular-nums",
  },

  // ── Bouton envoi ────────────────────────────────────────────────────
  sendBtn: {
    width: 32,
    height: 32,
    background: "var(--accent)",
    border: "none",
    borderRadius: 9,
    color: "#fff",
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    transition: "opacity 0.15s, background 0.12s",
    flexShrink: 0,
  },

  // ── Bouton stop ─────────────────────────────────────────────────────
  stopBtn: {
    width: 32,
    height: 32,
    background: "var(--stop-btn-bg)",
    border: "1px solid var(--stop-btn-border)",
    borderRadius: 9,
    color: "var(--stop-btn-color)",
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
  },

  // ── Pièces jointes ──────────────────────────────────────────────────
  attachBar: {
    display: "flex",
    flexWrap: "wrap",
    gap: 6,
    paddingBottom: 2,
  },
  attachItem: {
    display: "flex",
    alignItems: "center",
    gap: 5,
    background: "var(--attachment-item-bg)",
    border: "1px solid var(--attachment-item-border)",
    borderRadius: 8,
    padding: "3px 8px 3px 6px",
    fontSize: 12,
    maxWidth: 220,
  },
  attachIcon: { fontSize: 13, flexShrink: 0 },
  attachName: {
    color: "var(--attachment-name-color)",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
    flex: 1,
  },
  attachRemove: {
    background: "none",
    border: "none",
    cursor: "pointer",
    color: "var(--text-muted)",
    fontSize: 15,
    lineHeight: 1,
    padding: "0 1px",
    flexShrink: 0,
    fontFamily: "inherit",
  },

  // ── Menu attachement ────────────────────────────────────────────────
  attachMenu: {
    position: "absolute",
    bottom: "calc(100% + 6px)",
    left: 0,
    background: "var(--menu-bg)",
    border: "1px solid var(--menu-border)",
    borderRadius: 8,
    boxShadow: "0 4px 16px rgba(0,0,0,0.3)",
    zIndex: 100,
    overflow: "hidden",
    minWidth: 130,
  },
  attachMenuItem: {
    display: "block",
    width: "100%",
    background: "none",
    border: "none",
    padding: "8px 14px",
    textAlign: "left",
    cursor: "pointer",
    color: "var(--text-primary)",
    fontSize: 13,
    fontFamily: "inherit",
  },

  // ── Menu collections RAG ────────────────────────────────────────────
  ragMenu: {
    position: "absolute",
    bottom: "calc(100% + 8px)",
    left: 0,
    background: "var(--menu-bg)",
    border: "1px solid var(--rag-badge-on)",
    borderRadius: 10,
    boxShadow: "0 6px 20px rgba(0,0,0,0.3)",
    zIndex: 200,
    minWidth: 220,
    maxWidth: 300,
    maxHeight: 240,
    overflowY: "auto",
    padding: "4px 0",
  },
  ragMenuHeader: {
    padding: "6px 12px 4px",
    fontSize: 10,
    fontWeight: 600,
    color: "var(--rag-badge-on)",
    textTransform: "uppercase",
    letterSpacing: "0.06em",
    borderBottom: "1px solid var(--border)",
    marginBottom: 2,
  },
  ragMenuEmpty: {
    padding: "8px 12px",
    fontSize: 12,
    color: "var(--text-muted)",
    fontStyle: "italic",
  },
  ragMenuItem: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    width: "100%",
    background: "none",
    border: "none",
    padding: "7px 12px",
    textAlign: "left",
    cursor: "pointer",
    color: "var(--text-secondary)",
    fontSize: 12,
    fontFamily: "inherit",
    transition: "background 0.1s",
  },
  ragMenuItemActive: {
    background: "rgba(90,170,122,0.10)",
    color: "var(--text-primary)",
    fontWeight: 600,
  },

  // ── Barre de statut ─────────────────────────────────────────────────
  statusBar: {
    fontSize: 11,
    color: "var(--text-muted)",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
    textAlign: "center",
    padding: "0 4px",
  },

  // ── Hint clavier ────────────────────────────────────────────────────
  hint: {
    fontSize: 10,
    color: "var(--text-disabled)",
    textAlign: "center",
    userSelect: "none",
  },
  kbd: {
    background: "var(--elevated-bg)",
    border: "1px solid var(--border)",
    borderRadius: 3,
    padding: "1px 4px",
    fontFamily: "inherit",
    fontSize: 10,
    color: "var(--text-muted)",
  },

  // ── Menu rôles (pill compound) ──────────────────────────────────────
  profileMenu: {
    position: "absolute",
    bottom: "calc(100% + 8px)",
    left: 0,
    background: "var(--menu-bg)",
    border: "1px solid var(--accent)",
    borderRadius: 10,
    boxShadow: "0 6px 20px rgba(0,0,0,0.3)",
    zIndex: 200,
    minWidth: 200,
    maxWidth: 280,
    maxHeight: 240,
    overflowY: "auto",
    padding: "4px 0",
  },
  profileMenuHeader: {
    padding: "6px 12px 4px",
    fontSize: 10,
    fontWeight: 600,
    color: "var(--accent)",
    textTransform: "uppercase" as const,
    letterSpacing: "0.06em",
    borderBottom: "1px solid var(--border)",
    marginBottom: 2,
  },
  profileMenuEmpty: {
    padding: "8px 12px",
    fontSize: 12,
    color: "var(--text-muted)",
    fontStyle: "italic",
  },
  profileMenuItem: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    width: "100%",
    background: "none",
    border: "none",
    padding: "7px 12px",
    textAlign: "left" as const,
    cursor: "pointer",
    color: "var(--text-secondary)",
    fontSize: 12,
    fontFamily: "inherit",
    transition: "background 0.1s",
  },
  profileMenuItemActive: {
    background: "rgba(212,129,61,0.10)",
    color: "var(--text-primary)",
    fontWeight: 600,
  },
};
