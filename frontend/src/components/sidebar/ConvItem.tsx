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
 * ConvItem.tsx — Items de conversation : ConvItem (sidebar), DiscussionRow (panel discussions).
 * Inclut : AnchoredMenu, ConvContextMenu, useRenameState, timeAgo.
 */

import React, { useState, useRef, useEffect } from "react";
import { createPortal } from "react-dom";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { Conversation, Folder } from "../../hooks/useConversationTree";
import { IconChat } from "../ui/icons";
import { s } from "./sidebarStyles";

// ── timeAgo ───────────────────────────────────────────────────────────────────

export function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins  = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);
  const days  = Math.floor(diff / 86400000);
  if (mins < 1)   return "à l'instant";
  if (mins < 60)  return `il y a ${mins} minute${mins > 1 ? "s" : ""}`;
  if (hours < 24) return `il y a ${hours} heure${hours > 1 ? "s" : ""}`;
  if (days < 30)  return `il y a ${days} jour${days > 1 ? "s" : ""}`;
  const months = Math.floor(days / 30);
  return `il y a ${months} mois`;
}

// ── useRenameState ────────────────────────────────────────────────────────────

export function useRenameState(conv: Conversation, onRename?: (convId: string, title: string) => void) {
  const [isRenaming, setIsRenaming] = useState(false);
  const [renameVal, setRenameVal] = useState(conv.title);

  useEffect(() => {
    if (isRenaming) setRenameVal(conv.title);
  }, [isRenaming, conv.title]);

  function commitRename() {
    if (renameVal.trim() && onRename) onRename(conv.id, renameVal.trim());
    setIsRenaming(false);
  }

  return { isRenaming, setIsRenaming, renameVal, setRenameVal, commitRename };
}

// ── AnchoredMenu ──────────────────────────────────────────────────────────────

interface AnchoredMenuPos { top: number; left: number; openUp: boolean }

export function AnchoredMenu({
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

// ── ConvContextMenu ───────────────────────────────────────────────────────────

export function ConvContextMenu({
  conv, btnRef, menuOpen, setMenuOpen,
  showMoveMenu, setShowMoveMenu,
  onRename, onDelete, onStar, onMove, folders,
}: {
  conv: Conversation;
  btnRef: React.RefObject<HTMLButtonElement | null>;
  menuOpen: boolean;
  setMenuOpen: (v: boolean) => void;
  showMoveMenu: boolean;
  setShowMoveMenu: (v: boolean) => void;
  onRename?: () => void;
  onDelete?: (convId: string) => void;
  onStar?: (convId: string, starred: boolean) => void;
  onMove?: (convId: string, folderId: string | null) => void;
  folders?: Folder[];
}) {
  if (!menuOpen) return null;
  return (
    <AnchoredMenu anchorRef={btnRef} onClose={() => { setMenuOpen(false); setShowMoveMenu(false); }}>
      <button style={s.bubbleItem} onClick={(e) => { e.stopPropagation(); setMenuOpen(false); onRename?.(); }}>
        ✏️ Renommer
      </button>
      <button style={s.bubbleItem} onClick={(e) => { e.stopPropagation(); onStar?.(conv.id, !conv.starred); setMenuOpen(false); }}>
        {conv.starred ? "☆ Retirer des favoris" : "⭐ Ajouter aux favoris"}
      </button>
      {folders && folders.length > 0 && (
        <>
          <button style={s.bubbleItem} onClick={(e) => { e.stopPropagation(); setShowMoveMenu(!showMoveMenu); }}>
            📁 Déplacer {showMoveMenu ? "▲" : "▶"}
          </button>
          {showMoveMenu && (
            <div style={s.inlineSubmenu}>
              <button style={s.submenuItem} onClick={(e) => { e.stopPropagation(); onMove?.(conv.id, null); setMenuOpen(false); setShowMoveMenu(false); }}>
                📂 Sans dossier
              </button>
              {folders.map((f) => (
                <button key={f.id} style={s.submenuItem} onClick={(e) => { e.stopPropagation(); onMove?.(conv.id, f.id); setMenuOpen(false); setShowMoveMenu(false); }}>
                  📁 {f.name}
                </button>
              ))}
            </div>
          )}
        </>
      )}
      <div style={s.ctxSep} />
      <button style={{ ...s.bubbleItem, color: "#e07878" }} onClick={(e) => { e.stopPropagation(); onDelete?.(conv.id); setMenuOpen(false); }}>
        🗑️ Supprimer
      </button>
    </AnchoredMenu>
  );
}

// ── ConvItem ──────────────────────────────────────────────────────────────────

export function ConvItem({
  conv, isActive, onSelect, indent = 1,
  onRename, onDelete, onStar, onMove, folders,
}: {
  conv: Conversation;
  isActive: boolean;
  onSelect: () => void;
  indent?: number;
  onRename?: (convId: string, title: string) => void;
  onDelete?: (convId: string) => void;
  onStar?: (convId: string, starred: boolean) => void;
  onMove?: (convId: string, folderId: string | null) => void;
  folders?: Folder[];
}) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useSortable({
    id: conv.id,
    data: { type: "conv" },
  });

  const [menuOpen, setMenuOpen] = useState(false);
  const [showMoveMenu, setShowMoveMenu] = useState(false);
  const { isRenaming, setIsRenaming, renameVal, setRenameVal, commitRename } = useRenameState(conv, onRename);
  const btnRef = useRef<HTMLButtonElement>(null);

  const style: React.CSSProperties = {
    ...s.convRow,
    paddingLeft: 8 + indent * 14,
    background: isActive ? "var(--sidebar-item-active-bg)" : undefined,
    color: isActive ? "var(--sidebar-item-active-color)" : "var(--sidebar-item-color)",
    opacity: isDragging ? 0.4 : 1,
    transform: CSS.Translate.toString(transform),
    position: "relative",
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      className="conv-item-row"
      onClick={isRenaming ? undefined : onSelect}
      {...attributes}
      {...(isRenaming ? {} : listeners)}
    >
      <IconChat color={isActive ? "var(--accent)" : "var(--text-muted)"} size={13} />

      {isRenaming ? (
        <input
          value={renameVal}
          onChange={(e) => setRenameVal(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") commitRename();
            if (e.key === "Escape") setIsRenaming(false);
          }}
          onBlur={commitRename}
          onClick={(e) => e.stopPropagation()}
          style={{ ...s.inlineInput, flex: 1 }}
          autoFocus
        />
      ) : (
        <>
          <span style={s.convTitle} title={conv.title}>
            {conv.starred && <span style={{ marginRight: 3, fontSize: 11 }}>⭐</span>}
            {conv.title || "Sans titre"}
          </span>
          <button
            ref={btnRef}
            onClick={(e) => { e.stopPropagation(); setMenuOpen((v) => !v); setShowMoveMenu(false); }}
            style={s.menuDotBtn}
            className="conv-menu-btn"
            title="Actions"
          >
            ···
          </button>
        </>
      )}

      {menuOpen && (
        <ConvContextMenu
          conv={conv}
          btnRef={btnRef}
          menuOpen={menuOpen}
          setMenuOpen={setMenuOpen}
          showMoveMenu={showMoveMenu}
          setShowMoveMenu={setShowMoveMenu}
          onRename={() => setIsRenaming(true)}
          onDelete={onDelete}
          onStar={onStar}
          onMove={onMove}
          folders={folders}
        />
      )}
    </div>
  );
}

// ── DiscussionRow ─────────────────────────────────────────────────────────────

export function DiscussionRow({
  conv, isActive, onSelect, onRename, onDelete, onStar, onMove, folders,
}: {
  conv: Conversation;
  isActive: boolean;
  onSelect: () => void;
  onRename?: (convId: string, title: string) => void;
  onDelete?: (convId: string) => void;
  onStar?: (convId: string, starred: boolean) => void;
  onMove?: (convId: string, folderId: string | null) => void;
  folders?: Folder[];
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [showMoveMenu, setShowMoveMenu] = useState(false);
  const { isRenaming, setIsRenaming, renameVal, setRenameVal, commitRename } = useRenameState(conv, onRename);
  const btnRef = useRef<HTMLButtonElement>(null);

  return (
    <div
      style={{
        display: "flex", alignItems: "center",
        background: isActive ? "var(--sidebar-item-active-bg)" : "none",
        borderBottom: "1px solid var(--border)",
        padding: "0 8px 0 20px",
        transition: "background 0.1s",
        position: "relative",
      }}
      className="disc-row"
    >
      {isRenaming ? (
        <div style={{ flex: 1, padding: "10px 0" }}>
          <input
            value={renameVal}
            onChange={(e) => setRenameVal(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") commitRename();
              if (e.key === "Escape") setIsRenaming(false);
            }}
            onBlur={commitRename}
            style={{ ...s.inlineInput, width: "100%", boxSizing: "border-box" }}
            autoFocus
          />
        </div>
      ) : (
        <button
          onClick={onSelect}
          style={{
            flex: 1, background: "none", border: "none", padding: "12px 0",
            textAlign: "left", cursor: "pointer", fontFamily: "inherit", minWidth: 0,
          }}
        >
          <div style={{
            fontSize: 14, fontWeight: isActive ? 600 : 400,
            color: "var(--text-primary)", overflow: "hidden",
            textOverflow: "ellipsis", whiteSpace: "nowrap", marginBottom: 3,
            display: "flex", alignItems: "center", gap: 4,
          }}>
            {conv.starred && <span style={{ fontSize: 12, flexShrink: 0 }}>⭐</span>}
            {conv.title || "Sans titre"}
          </div>
          <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
            Dernier message {timeAgo(conv.updated_at)}
          </div>
        </button>
      )}

      <button
        ref={btnRef}
        onClick={(e) => { e.stopPropagation(); setMenuOpen((v) => !v); setShowMoveMenu(false); }}
        style={{ ...s.menuDotBtn, flexShrink: 0 }}
        className="disc-menu-btn"
        title="Actions"
      >
        ···
      </button>

      <ConvContextMenu
        conv={conv}
        btnRef={btnRef}
        menuOpen={menuOpen}
        setMenuOpen={setMenuOpen}
        showMoveMenu={showMoveMenu}
        setShowMoveMenu={setShowMoveMenu}
        onRename={() => setIsRenaming(true)}
        onDelete={onDelete}
        onStar={onStar}
        onMove={onMove}
        folders={folders}
      />
    </div>
  );
}
