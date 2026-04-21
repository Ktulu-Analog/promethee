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
 * ProjectsPanel.tsx — Panneau de gestion des projets (dossiers de conversation)
 *
 * overlay plein écran, grille de cartes, barre de recherche,
 * formulaire de création inline avec titre + description.
 * Les descriptions sont stockées en localStorage (clé : proj_desc_{folderId}).
 *
 * Props :
 *   folders          — Liste des dossiers racine
 *   activeFolder     — Dossier actuellement sélectionné
 *   onSelectFolder   — Sélectionne un dossier et ferme le panneau
 *   onCreateFolder   — Crée un nouveau dossier avec nom + description
 *   onRenameFolder   — Renomme un dossier existant
 *   onDeleteFolder   — Supprime un dossier
 *   onClose          — Ferme le panneau
 */

import React, { useState, useRef, useEffect } from "react";
import { createPortal } from "react-dom";
import type { Folder, Conversation } from "../../hooks/useConversationTree";

// ── Helpers localStorage pour les descriptions ────────────────────────────────

export const projDescKey = (id: string) => `proj_desc_${id}`;

export const getDesc = (id: string) => {
  try { return localStorage.getItem(projDescKey(id)) ?? ""; } catch { return ""; }
};

export const setDesc = (id: string, desc: string) => {
  try { localStorage.setItem(projDescKey(id), desc); } catch {}
};

// ── AnchoredMenu ──────────────────────────────────────────────────────────────
// Menu rendu en position: fixed, ancré sous le bouton déclencheur.
// Calcule automatiquement si le menu doit s'ouvrir vers le haut ou le bas.

interface AnchoredMenuPos { top: number; left: number; openUp: boolean }

function AnchoredMenu({
  anchorRef, onClose, children,
}: {
  anchorRef: React.RefObject<HTMLButtonElement | null>;
  onClose: () => void;
  children: React.ReactNode;
}) {
  const [pos, setPos] = useState<AnchoredMenuPos | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const MENU_HEIGHT_ESTIMATE = 180;

  useEffect(() => {
    if (!anchorRef.current) return;
    const r = anchorRef.current.getBoundingClientRect();
    const spaceBelow = window.innerHeight - r.bottom;
    const openUp = spaceBelow < MENU_HEIGHT_ESTIMATE && r.top > MENU_HEIGHT_ESTIMATE;
    setPos({
      top: openUp ? r.top : r.bottom + 4,
      left: Math.min(r.right - 180, window.innerWidth - 196),
      openUp,
    });
  }, []);

  useEffect(() => {
    function handleOut(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node) &&
          anchorRef.current && !anchorRef.current.contains(e.target as Node)) {
        onClose();
      }
    }
    window.addEventListener("mousedown", handleOut);
    return () => window.removeEventListener("mousedown", handleOut);
  }, [onClose]);

  if (!pos) return null;

  return createPortal(
    <div
      ref={menuRef}
      style={{
        position: "fixed",
        top: pos.openUp ? "auto" : pos.top,
        bottom: pos.openUp ? window.innerHeight - pos.top : "auto",
        left: Math.max(8, pos.left),
        zIndex: 99999,
        background: "var(--menu-bg)",
        border: "1px solid var(--menu-border)",
        borderRadius: 8,
        boxShadow: "0 6px 24px rgba(0,0,0,0.25)",
        minWidth: 180,
        padding: "3px 0",
      }}
      onMouseDown={(e) => e.stopPropagation()}
    >
      {children}
    </div>,
    document.body
  );
}

// ── ProjectCard ───────────────────────────────────────────────────────────────

function ProjectCard({
  folder, isActive, conversations, onSelect, onOpenFolder, onRename, onDelete,
}: {
  folder: Folder;
  isActive: boolean;
  conversations: Conversation[];
  onSelect: () => void;
  onOpenFolder: () => void;
  onRename: () => void;
  onDelete: () => void;
}) {
  const [menuOpen, setMenuOpen]       = useState(false);
  const [expanded, setExpanded]       = useState(false);
  const btnRef = useRef<HTMLButtonElement>(null);
  const desc = getDesc(folder.id);
  const count = conversations.length;

  // Date relative approximative (on n'a pas updated_at dans Folder, on affiche created_at)
  const dateStr = (() => {
    try {
      const d = new Date((folder as any).created_at ?? "");
      if (isNaN(d.getTime())) return "";
      const diff = Date.now() - d.getTime();
      const sec  = Math.floor(diff / 1000);
      if (sec < 60)   return `il y a ${sec} seconde${sec !== 1 ? "s" : ""}`;
      const min  = Math.floor(sec / 60);
      if (min < 60)   return `il y a ${min} minute${min !== 1 ? "s" : ""}`;
      const h    = Math.floor(min / 60);
      if (h < 24)     return `il y a ${h} heure${h !== 1 ? "s" : ""}`;
      const day  = Math.floor(h / 24);
      if (day < 30)   return `il y a ${day} jour${day !== 1 ? "s" : ""}`;
      return d.toLocaleDateString("fr-FR", { day: "2-digit", month: "short", year: "numeric" });
    } catch { return ""; }
  })();

  return (
    <div
      style={{
        ...sp.card,
        border: isActive
          ? "1px solid var(--accent, #d4813d)"
          : "1px solid var(--border, rgba(0,0,0,0.12))",
        boxShadow: isActive ? "0 0 0 2px rgba(212,129,61,0.12)" : sp.card.boxShadow,
        flexDirection: "column",
        alignItems: "stretch",
        gap: 0,
        padding: 0,
        cursor: "default",
      }}
    >
      {/* ── En-tête cliquable ── */}
      <div
        style={{ display: "flex", alignItems: "flex-start", padding: "18px 16px 14px", cursor: "pointer", gap: 8 }}
        onClick={() => setExpanded(v => !v)}
      >
        <div style={{ flex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
            <span style={sp.cardName}>{folder.name}</span>
            <span style={sp.convBadge}>
              {count} conversation{count !== 1 ? "s" : ""}
            </span>
          </div>
          {desc && <div style={sp.cardDesc}>{desc}</div>}
          {dateStr && <div style={sp.cardDate}>Mis.e.s à jour {dateStr}</div>}
        </div>

        {/* Chevron */}
        <span style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2, transition: "transform 0.2s", transform: expanded ? "rotate(180deg)" : "rotate(0deg)", display: "inline-block" }}>
          ▼
        </span>

        {/* Menu ··· */}
        <button
          ref={btnRef}
          style={sp.cardMenu}
          title="Actions"
          onClick={e => { e.stopPropagation(); setMenuOpen(v => !v); }}
        >
          ···
        </button>
      </div>

      {/* ── Panneau dépliable ── */}
      {expanded && (
        <div style={sp.expandedPanel}>
          {count === 0 ? (
            <div style={sp.convEmpty}>Aucune conversation dans ce dossier.</div>
          ) : (
            <ul style={sp.convList}>
              {conversations.map(conv => (
                <li key={conv.id} style={sp.convItem}>
                  <span style={sp.convBullet}>💬</span>
                  <span style={sp.convTitle}>{conv.title || "Sans titre"}</span>
                </li>
              ))}
            </ul>
          )}
          {/* Bouton ouvrir le dossier */}
          <button
            style={sp.openFolderBtn}
            onClick={e => { e.stopPropagation(); onOpenFolder(); }}
          >
            📂 Ouvrir ce dossier dans les conversations
          </button>
        </div>
      )}

      {menuOpen && (
        <AnchoredMenu anchorRef={btnRef} onClose={() => setMenuOpen(false)}>
          <button style={sp.menuItem} onClick={e => { e.stopPropagation(); setMenuOpen(false); onRename(); }}>
            ✏️ Renommer
          </button>
          <div style={sp.menuSep} />
          <button style={{ ...sp.menuItem, color: "#e07878" }} onClick={e => { e.stopPropagation(); setMenuOpen(false); onDelete(); }}>
            🗑️ Supprimer
          </button>
        </AnchoredMenu>
      )}
    </div>
  );
}

// ── ProjectsPanel ─────────────────────────────────────────────────────────────

export function ProjectsPanel({
  folders, activeFolder, conversationsByFolder, onSelectFolder, onCreateFolder,
  onRenameFolder, onDeleteFolder, onClose,
}: {
  folders: Folder[];
  activeFolder: Folder | null;
  conversationsByFolder: Record<string, Conversation[]>;
  onSelectFolder: (folder: Folder | null) => void;
  onCreateFolder: (name: string, description: string) => void;
  onRenameFolder: (folderId: string, currentName: string) => void;
  onDeleteFolder: (folderId: string, name: string) => void;
  onClose: () => void;
}) {
  const [search, setSearch]         = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName]       = useState("");
  const [newDesc, setNewDesc]       = useState("");
  const [, forceUpdate]             = useState(0); // pour relire localStorage après création

  const filtered = folders.filter(f =>
    f.name.toLowerCase().includes(search.toLowerCase())
  );

  function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!newName.trim()) return;
    onCreateFolder(newName.trim(), newDesc.trim());
    setNewName("");
    setNewDesc("");
    setShowCreate(false);
    setTimeout(() => forceUpdate(n => n + 1), 100); // relire les descs après création
  }

  // ── Overlay plein écran ──────────────────────────────────────────────────
  return (
    <div style={sp.overlay} onClick={onClose}>
      <div style={sp.container} onClick={e => e.stopPropagation()}>

        {/* ── Formulaire de création ── */}
        {showCreate ? (
          <div style={sp.createWrap}>
            <h2 style={sp.createTitle}>Créer un dossier personnel</h2>

            {/* Encart d'aide */}
            <div style={sp.helpBox}>
              <p style={sp.helpTitle}>Comment utiliser les dossiers ?</p>
              <p style={sp.helpText}>
                Les dossiers permettent d'organiser vos conversations par thème.
                Commencez par créer un titre et une description.
                Vous pourrez toujours les modifier ultérieurement.
              </p>
            </div>

            <form onSubmit={handleCreate} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <div style={sp.fieldGroup}>
                <label style={sp.fieldLabel}>Sur quoi travaillez-vous ?</label>
                <input
                  style={sp.fieldInput}
                  placeholder="Nommez votre dossier"
                  value={newName}
                  onChange={e => setNewName(e.target.value)}
                  autoFocus
                  required
                />
              </div>
              <div style={sp.fieldGroup}>
                <label style={sp.fieldLabel}>Qu'essayez-vous de faire ?</label>
                <textarea
                  style={sp.fieldTextarea}
                  placeholder="Décrivez votre dossier, vos objectifs, le sujet, etc..."
                  value={newDesc}
                  onChange={e => setNewDesc(e.target.value)}
                  rows={3}
                />
              </div>
              <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, marginTop: 4 }}>
                <button type="button" style={sp.btnCancel}
                  onClick={() => { setShowCreate(false); setNewName(""); setNewDesc(""); }}>
                  Annuler
                </button>
                <button type="submit" style={sp.btnCreate} disabled={!newName.trim()}>
                  Créer un dossier
                </button>
              </div>
            </form>
          </div>

        ) : (
          /* ── Liste des dossiers ── */
          <>
            <div style={sp.header}>
              <h1 style={sp.mainTitle}>Dossiers</h1>
              <button style={sp.newBtn} onClick={() => setShowCreate(true)}>
                <span style={{ fontSize: 16, lineHeight: 1 }}>+</span>
                <span>Nouveau dossier</span>
              </button>
            </div>

            {/* Barre de recherche */}
            <div style={sp.searchWrap}>
              <span style={sp.searchIcon}>🔍</span>
              <input
                style={sp.searchInput}
                placeholder="Rechercher des dossiers..."
                value={search}
                onChange={e => setSearch(e.target.value)}
                autoFocus
              />
            </div>

            {/* Tri (cosmétique) */}
            <div style={sp.sortRow}>
              <span style={sp.sortLabel}>Trier par</span>
              <span style={sp.sortChip}>Activité ∨</span>
            </div>

            {/* Grille de cartes */}
            {filtered.length === 0 ? (
              <div style={sp.empty}>
                {search ? "Aucun dossier ne correspond à votre recherche." : (
                  <>Aucun dossier pour l'instant.<br />Créez-en un pour organiser vos conversations.</>
                )}
              </div>
            ) : (
              <div style={sp.grid}>
                {filtered.map(folder => (
                  <ProjectCard
                    key={folder.id}
                    folder={folder}
                    isActive={activeFolder?.id === folder.id}
                    conversations={conversationsByFolder[folder.id] ?? []}
                    onSelect={() => { onSelectFolder(folder); onClose(); }}
                    onOpenFolder={() => { onSelectFolder(folder); onClose(); }}
                    onRename={() => onRenameFolder(folder.id, folder.name)}
                    onDelete={() => onDeleteFolder(folder.id, folder.name)}
                  />
                ))}
              </div>
            )}

            {/* Bouton fermer */}
            <button style={sp.closeBtn} onClick={onClose} title="Fermer">✕</button>
          </>
        )}
      </div>
    </div>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────

const sp: Record<string, React.CSSProperties> = {
  overlay: {
    position: "fixed", inset: 0, zIndex: 200,
    background: "rgba(0,0,0,0.25)",
    display: "flex", alignItems: "flex-start", justifyContent: "center",
    paddingTop: 60,
    backdropFilter: "blur(2px)",
  },
  container: {
    position: "relative",
    background: "var(--base-bg, #fff)",
    borderRadius: 14,
    width: "min(860px, 92vw)",
    maxHeight: "82vh",
    overflowY: "auto",
    padding: "40px 48px 48px",
    boxShadow: "0 8px 40px rgba(0,0,0,0.18)",
  },
  // ── En-tête liste ──────────────────────────────────────────────────────────
  header: {
    display: "flex", alignItems: "center", justifyContent: "space-between",
    marginBottom: 24,
  },
  mainTitle: {
    margin: 0, fontSize: 26, fontWeight: 700,
    color: "var(--text-primary)",
    fontFamily: "inherit",
  },
  newBtn: {
    display: "flex", alignItems: "center", gap: 6,
    background: "var(--text-primary, #1a1a1e)",
    color: "var(--base-bg, #fff)",
    border: "none", borderRadius: 8,
    padding: "8px 16px", fontSize: 14, fontWeight: 600,
    cursor: "pointer", fontFamily: "inherit",
  },
  searchWrap: {
    position: "relative", marginBottom: 16,
    display: "flex", alignItems: "center",
  },
  searchIcon: {
    position: "absolute", left: 12, fontSize: 14, pointerEvents: "none",
    opacity: 0.5,
  },
  searchInput: {
    width: "100%", padding: "10px 14px 10px 36px",
    background: "var(--input-bg, rgba(0,0,0,0.04))",
    border: "1px solid var(--border, rgba(0,0,0,0.15))",
    borderRadius: 8, fontSize: 14,
    color: "var(--text-primary)", outline: "none",
    boxSizing: "border-box" as const,
    fontFamily: "inherit",
  },
  sortRow: {
    display: "flex", alignItems: "center", justifyContent: "flex-end",
    gap: 6, marginBottom: 20, fontSize: 13, color: "var(--text-muted)",
  },
  sortLabel: { fontSize: 13, color: "var(--text-muted)" },
  sortChip: {
    fontSize: 13, color: "var(--text-secondary)",
    padding: "2px 8px", border: "1px solid var(--border, rgba(0,0,0,0.12))",
    borderRadius: 6, cursor: "default",
  },
  // ── Grille de cartes ───────────────────────────────────────────────────────
  grid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))",
    gap: 16,
  },
  card: {
    display: "flex", alignItems: "flex-start",
    background: "var(--surface-bg, rgba(0,0,0,0.03))",
    borderRadius: 10,
    padding: "18px 16px",
    cursor: "pointer",
    transition: "box-shadow 0.15s, border-color 0.15s",
    boxShadow: "0 1px 3px rgba(0,0,0,0.06)",
    gap: 8,
  },
  cardName: {
    fontSize: 15, fontWeight: 600,
    color: "var(--text-primary)", marginBottom: 4,
  },
  cardDesc: {
    fontSize: 12, color: "var(--text-secondary)",
    marginBottom: 6, lineHeight: 1.4,
    display: "-webkit-box" as any,
    WebkitLineClamp: 2, WebkitBoxOrient: "vertical" as any,
    overflow: "hidden",
  },
  cardDate: {
    fontSize: 11, color: "var(--text-muted)",
  },
  cardMenu: {
    flexShrink: 0,
    background: "none", border: "none",
    color: "var(--text-muted)", fontSize: 16,
    cursor: "pointer", padding: "0 2px",
    borderRadius: 4, lineHeight: 1,
  },
  // ── Menu contextuel carte ──────────────────────────────────────────────────
  menuItem: {
    display: "block" as const,
    width: "100%",
    background: "none",
    border: "none",
    padding: "7px 14px",
    textAlign: "left" as const,
    cursor: "pointer",
    fontSize: 13,
    color: "var(--menu-color, var(--text-primary))",
    fontFamily: "inherit",
    whiteSpace: "nowrap" as const,
  },
  menuSep: {
    height: 1,
    background: "var(--border)",
    margin: "3px 0",
  },
  // ── Formulaire de création ─────────────────────────────────────────────────
  createWrap: {
    maxWidth: 540, margin: "0 auto",
    display: "flex", flexDirection: "column", gap: 20,
  },
  createTitle: {
    margin: 0, fontSize: 26, fontWeight: 700,
    color: "var(--text-primary)", textAlign: "center" as const,
    fontFamily: "inherit",
  },
  helpBox: {
    background: "var(--elevated-bg, rgba(0,0,0,0.04))",
    border: "1px solid var(--border, rgba(0,0,0,0.1))",
    borderRadius: 10, padding: "16px 18px",
  },
  helpTitle: {
    margin: "0 0 6px", fontSize: 14, fontWeight: 600,
    color: "var(--text-primary)",
  },
  helpText: {
    margin: 0, fontSize: 13, color: "var(--text-secondary)", lineHeight: 1.5,
  },
  fieldGroup: {
    display: "flex", flexDirection: "column", gap: 6,
  },
  fieldLabel: {
    fontSize: 13, fontWeight: 500, color: "var(--text-secondary)",
  },
  fieldInput: {
    padding: "10px 12px",
    background: "var(--input-bg, #fff)",
    border: "2px solid var(--accent, #1a73e8)",
    borderRadius: 8, fontSize: 14,
    color: "var(--text-primary)", outline: "none",
    fontFamily: "inherit",
  },
  fieldTextarea: {
    padding: "10px 12px",
    background: "var(--input-bg, rgba(0,0,0,0.03))",
    border: "1px solid var(--border, rgba(0,0,0,0.15))",
    borderRadius: 8, fontSize: 14,
    color: "var(--text-primary)", outline: "none",
    fontFamily: "inherit", resize: "vertical" as const,
    lineHeight: 1.5,
  },
  btnCancel: {
    padding: "9px 20px",
    background: "none", border: "1px solid var(--border, rgba(0,0,0,0.2))",
    borderRadius: 8, fontSize: 14, fontWeight: 500,
    color: "var(--text-secondary)", cursor: "pointer", fontFamily: "inherit",
  },
  btnCreate: {
    padding: "9px 20px",
    background: "var(--text-primary, #1a1a1e)", color: "var(--base-bg, #fff)",
    border: "none", borderRadius: 8, fontSize: 14, fontWeight: 600,
    cursor: "pointer", fontFamily: "inherit",
  },
  // ── Conversations dépliables ───────────────────────────────────────────────
  convBadge: {
    fontSize: 11, fontWeight: 500,
    color: "var(--text-muted)",
    background: "var(--elevated-bg, rgba(0,0,0,0.06))",
    borderRadius: 10, padding: "1px 7px",
    whiteSpace: "nowrap" as const,
    flexShrink: 0,
  },
  expandedPanel: {
    borderTop: "1px solid var(--border, rgba(0,0,0,0.08))",
    padding: "10px 16px 14px",
    display: "flex", flexDirection: "column" as const, gap: 6,
  },
  convList: {
    listStyle: "none", margin: 0, padding: 0,
    display: "flex", flexDirection: "column" as const, gap: 3,
  },
  convItem: {
    display: "flex", alignItems: "center", gap: 6,
    padding: "4px 0",
  },
  convBullet: {
    fontSize: 12, flexShrink: 0, opacity: 0.6,
  },
  convTitle: {
    fontSize: 12, color: "var(--text-secondary)",
    overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" as const,
  },
  convEmpty: {
    fontSize: 12, color: "var(--text-muted)",
    fontStyle: "italic", padding: "2px 0 6px",
  },
  openFolderBtn: {
    marginTop: 6,
    display: "inline-flex", alignItems: "center", gap: 6,
    background: "var(--surface-bg, rgba(0,0,0,0.04))",
    border: "1px solid var(--border, rgba(0,0,0,0.12))",
    borderRadius: 7, padding: "6px 12px",
    fontSize: 12, fontWeight: 500,
    color: "var(--text-secondary)", cursor: "pointer",
    fontFamily: "inherit",
    alignSelf: "flex-start" as const,
  },
  // ── Divers ─────────────────────────────────────────────────────────────────
  empty: {
    padding: "48px 0", textAlign: "center" as const,
    color: "var(--text-muted)", fontSize: 14, lineHeight: 1.6,
  },
  closeBtn: {
    position: "absolute" as const, top: 16, right: 20,
    background: "none", border: "none",
    color: "var(--text-muted)", fontSize: 18,
    cursor: "pointer", padding: "4px 8px", borderRadius: 6,
  },
};
